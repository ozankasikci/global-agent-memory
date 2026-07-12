from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from global_memory.application.memory_service import MemoryService
from global_memory.domain.models import MemoryDraft
from global_memory.embeddings.fake import FakeEmbeddingProvider
from global_memory.index.database import IndexDatabase
from global_memory.index.embedding_indexer import EmbeddingIndexer
from global_memory.index.indexer import Indexer
from global_memory.index.vectors import SqliteVecStore
from global_memory.mcp.daemon import retry_pending_embeddings
from global_memory.mcp.server import _status, build_container
from global_memory.projects.models import ProjectDraft
from global_memory.retrieval.search import SearchRequest
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
        "INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)",
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
            "standard",
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
    indexed = database.connection.execute(
        "SELECT c.id, d.path FROM chunks c JOIN documents d ON d.id=c.document_id LIMIT 1"
    ).fetchone()
    old_chunk = indexed["id"]

    path = tmp_path / "vault" / indexed["path"]
    path.write_text(path.read_text().replace("input conveyor", "output conveyor"))
    keyword.index_path(path.relative_to(tmp_path / "vault"))
    new_chunk = database.connection.execute("SELECT id FROM chunks").fetchone()[0]
    assert new_chunk != old_chunk

    report = embeddings.sync(provider)
    assert report.embedded == 1
    assert database.connection.execute("SELECT COUNT(*) FROM vector_entries").fetchone()[0] == 1


def test_embedding_retries_are_persisted_backed_off_and_bounded(tmp_path: Path) -> None:
    database, _ = setup_index(tmp_path)
    current = NOW
    embeddings = EmbeddingIndexer(
        database,
        SqliteVecStore(database),
        clock=lambda: current,
        max_attempts=3,
    )
    failing = FakeEmbeddingProvider(model="offline", dimension=8, available=False)

    assert embeddings.sync(failing).failed == 1
    assert embeddings.sync(failing).failed == 0
    current += timedelta(seconds=1)
    assert embeddings.sync(failing).failed == 1
    current += timedelta(seconds=2)
    assert embeddings.sync(failing).failed == 1
    job = database.connection.execute("SELECT status, attempts, next_attempt_at FROM embedding_jobs").fetchone()
    assert tuple(job) == ("failed", 3, None)
    assert embeddings.sync(failing).failed == 0


def test_shared_container_wires_semantics_and_degrades_when_provider_is_offline(tmp_path: Path) -> None:
    setup_index(tmp_path)
    failing = FakeEmbeddingProvider(model="offline", dimension=8, available=False)

    container = build_container(
        tmp_path / "vault",
        tmp_path / "data",
        transport="test",
        embedding_provider=failing,
    )
    container.projects.add(ProjectDraft(name="Factory"))
    page = container.search.search(
        SearchRequest(query="furnace", project="Factory", mode="hybrid", include_candidates=True)
    )

    assert page.results
    assert page.mode_used == "keyword"
    assert "semantic_unavailable_keyword_fallback" in page.warnings
    assert (
        container.database.connection.execute("SELECT COUNT(*) FROM embedding_jobs WHERE status='pending'").fetchone()[
            0
        ]
        == 1
    )

    for _ in range(4):
        container.database.connection.execute("UPDATE embedding_jobs SET next_attempt_at=NULL")
        container.embedding_indexer.sync(failing)

    job = container.database.connection.execute("SELECT status, attempts FROM embedding_jobs").fetchone()
    status = _status(container)
    assert tuple(job) == ("failed", 5)
    assert status["pending_embedding_jobs"] == 0
    assert status["keyword_only"] is True


@pytest.mark.asyncio
async def test_daemon_retries_due_embedding_work_while_idle(tmp_path: Path) -> None:
    setup_index(tmp_path)
    provider = FakeEmbeddingProvider(model="recovering", dimension=8, available=False)
    container = build_container(
        tmp_path / "vault",
        tmp_path / "data",
        transport="test",
        embedding_provider=provider,
    )
    container.database.connection.execute("UPDATE embedding_jobs SET next_attempt_at=NULL WHERE status='pending'")
    provider.available = True

    task = asyncio.create_task(retry_pending_embeddings(container, provider, batch_size=8, interval_seconds=0.01))
    try:
        deadline = asyncio.get_running_loop().time() + 1
        while asyncio.get_running_loop().time() < deadline:
            pending = container.database.connection.execute(
                "SELECT COUNT(*) FROM embedding_jobs WHERE status='pending'"
            ).fetchone()[0]
            if pending == 0:
                break
            await asyncio.sleep(0.01)
        else:
            raise AssertionError("idle embedding retry did not complete")
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert container.database.connection.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0] > 0
