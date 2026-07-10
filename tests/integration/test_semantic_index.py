from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from global_memory.application.memory_service import MemoryService
from global_memory.domain.models import MemoryDraft
from global_memory.embeddings.fake import FakeEmbeddingProvider
from global_memory.index.database import IndexDatabase
from global_memory.index.embedding_indexer import EmbeddingIndexer
from global_memory.index.indexer import Indexer
from global_memory.index.vectors import SqliteVecStore
from global_memory.vault.repository import VaultRepository

pytestmark = pytest.mark.integration
NOW = datetime(2026, 7, 11, 12, 0, tzinfo=UTC)


def setup_index(tmp_path: Path) -> tuple[IndexDatabase, Indexer]:
    vault = tmp_path / "vault"
    repository = VaultRepository(vault, tmp_path / "data" / "audit.jsonl", clock=lambda: NOW)
    MemoryService(repository).remember(
        MemoryDraft(
            title="Semantic note",
            content="# Summary\n\nA furnace accepts ore from an input conveyor.\n",
            type="solution",
            scope="project",
            project="Factory",
        )
    )
    database = IndexDatabase(tmp_path / "data" / "memory.db")
    indexer = Indexer(vault, database)
    indexer.full_reindex()
    return database, indexer


def test_real_sqlite_vec_store_orders_cosine_matches(tmp_path: Path) -> None:
    database = IndexDatabase(tmp_path / "vectors.db")
    database.connection.execute(
        "INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)",
        (
            "mem_a",
            "a.md",
            "A",
            "fact",
            "global",
            None,
            "active",
            1,
            1,
            NOW.isoformat(),
            NOW.isoformat(),
            "a",
            "{}",
            NOW.isoformat(),
        ),
    )
    for chunk_id in ("chunk_a", "chunk_b"):
        database.connection.execute(
            "INSERT INTO chunks VALUES (?, 'mem_a', ?, NULL, ?, ?, 1)",
            (chunk_id, 0 if chunk_id == "chunk_a" else 1, chunk_id, chunk_id),
        )
    vectors = SqliteVecStore(database)
    assert vectors.available
    vectors.upsert("chunk_a", "fake", "m", "ha", [1.0, 0.0])
    vectors.upsert("chunk_b", "fake", "m", "hb", [0.0, 1.0])
    matches = vectors.search("fake", "m", [0.9, 0.1], limit=2)
    assert [match.chunk_id for match in matches] == ["chunk_a", "chunk_b"]


def test_changed_only_model_invalidation_and_outage_fallback(tmp_path: Path) -> None:
    database, keyword = setup_index(tmp_path)
    vectors = SqliteVecStore(database)
    embeddings = EmbeddingIndexer(database, vectors)
    first_provider = FakeEmbeddingProvider(model="fake-a", dimension=8)

    first = embeddings.sync(first_provider, batch_size=8)
    second = embeddings.sync(first_provider, batch_size=8)
    assert first.embedded == 1
    assert second.embedded == 0 and second.skipped == 1
    assert len(first_provider.calls) == 1

    changed_provider = FakeEmbeddingProvider(model="fake-b", dimension=8)
    changed = embeddings.sync(changed_provider, batch_size=8)
    assert changed.embedded == 1
    models = database.connection.execute("SELECT DISTINCT model FROM embeddings").fetchall()
    assert [row[0] for row in models] == ["fake-b"]

    resized_provider = FakeEmbeddingProvider(model="fake-b", dimension=12)
    resized = embeddings.sync(resized_provider, batch_size=8)
    assert resized.embedded == 1
    assert database.connection.execute("SELECT dimension FROM embeddings").fetchone()[0] == 12

    failing = FakeEmbeddingProvider(model="fake-c", dimension=8, available=False)
    degraded = embeddings.sync(failing, batch_size=8)
    assert degraded.failed == 1
    assert degraded.keyword_only
    job = database.connection.execute("SELECT status, attempts FROM embedding_jobs").fetchone()
    assert tuple(job) == ("pending", 1)
    assert keyword.keyword_search("furnace")


def test_replaced_chunks_prune_stale_sqlite_vec_rows(tmp_path: Path) -> None:
    database, keyword = setup_index(tmp_path)
    vectors = SqliteVecStore(database)
    embeddings = EmbeddingIndexer(database, vectors)
    provider = FakeEmbeddingProvider(model="fake", dimension=8)
    embeddings.sync(provider)
    old_chunk = database.connection.execute("SELECT id FROM chunks").fetchone()[0]

    path = next((tmp_path / "vault").rglob("*.md"))
    path.write_text(path.read_text().replace("input conveyor", "output conveyor"))
    keyword.index_path(path.relative_to(tmp_path / "vault"))
    new_chunk = database.connection.execute("SELECT id FROM chunks").fetchone()[0]
    assert new_chunk != old_chunk

    report = embeddings.sync(provider)
    assert report.embedded == 1
    assert database.connection.execute("SELECT COUNT(*) FROM vector_entries").fetchone()[0] == 1
