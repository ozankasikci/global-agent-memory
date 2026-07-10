from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from global_memory.domain.models import MemoryMetadata
from global_memory.embeddings.fake import FakeEmbeddingProvider
from global_memory.errors import ErrorCode, GlobalMemoryError
from global_memory.index.database import IndexDatabase
from global_memory.index.indexer import Indexer
from global_memory.index.vectors import FakeVectorStore
from global_memory.retrieval.context import ContextPacker
from global_memory.retrieval.search import SearchRequest, SearchService
from global_memory.vault.markdown import render_note

pytestmark = pytest.mark.integration
NOW = datetime(2026, 7, 11, 13, 0, tzinfo=UTC)


def write_note(
    vault: Path,
    memory_id: str,
    title: str,
    body: str,
    *,
    scope: str,
    project: str | None = None,
    status: str = "active",
    memory_type: str = "fact",
    importance: float = 0.5,
    age_minutes: int = 0,
) -> None:
    timestamp = NOW - timedelta(minutes=age_minutes)
    metadata = MemoryMetadata.model_validate(
        {
            "id": memory_id,
            "title": title,
            "type": memory_type,
            "scope": scope,
            "project": project,
            "status": status,
            "confidence": 0.8,
            "importance": importance,
            "created_at": timestamp,
            "updated_at": timestamp,
            "tags": ["automation", project.lower() if project else scope],
            "links": [],
            "source_kind": "manual",
            "source_ref": None,
            "supersedes": [],
            "superseded_by": "mem_replacement" if status == "superseded" else None,
        }
    )
    path = vault / f"notes/{memory_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_note(metadata, body))


def fixture(tmp_path: Path) -> tuple[IndexDatabase, Indexer]:
    vault = tmp_path / "vault"
    write_note(
        vault,
        "mem_alpha",
        "Alpha conveyor",
        "Project Alpha conveyor intake.",
        scope="project",
        project="Alpha",
        importance=0.9,
    )
    write_note(vault, "mem_beta", "Beta conveyor", "Project Beta conveyor intake.", scope="project", project="Beta")
    write_note(
        vault, "mem_global", "Global conveyor", "Global conveyor convention.", scope="global", memory_type="convention"
    )
    write_note(vault, "mem_org", "Organization conveyor", "Organization conveyor rule.", scope="organization")
    write_note(
        vault,
        "mem_session",
        "Alpha session",
        "Alpha conveyor session summary.",
        scope="project",
        project="Alpha",
        memory_type="session_summary",
    )
    write_note(
        vault,
        "mem_candidate",
        "Candidate conveyor",
        "Candidate conveyor idea.",
        scope="project",
        project="Alpha",
        status="candidate",
    )
    write_note(
        vault, "mem_archived", "Archived conveyor", "Archived conveyor history.", scope="archive", status="archived"
    )
    write_note(
        vault,
        "mem_rejected",
        "Rejected conveyor",
        "Rejected conveyor idea.",
        scope="project",
        project="Alpha",
        status="rejected",
    )
    write_note(
        vault,
        "mem_old",
        "Old conveyor",
        "Superseded conveyor rule.",
        scope="project",
        project="Alpha",
        status="superseded",
    )
    database = IndexDatabase(tmp_path / "data" / "memory.db")
    indexer = Indexer(vault, database)
    indexer.full_reindex()
    return database, indexer


def test_default_project_and_status_isolation_with_complete_fields(tmp_path: Path) -> None:
    database, indexer = fixture(tmp_path)
    service = SearchService(database, indexer, vault_name="Global Memory")
    page = service.search(SearchRequest(query="conveyor", project="Alpha", mode="keyword", limit=20))
    ids = [result.memory_id for result in page.results]
    assert set(ids) == {"mem_alpha", "mem_global", "mem_org", "mem_session"}
    assert "mem_beta" not in ids
    assert ids.index("mem_alpha") < ids.index("mem_session")
    alpha = next(result for result in page.results if result.memory_id == "mem_alpha")
    assert alpha.path == "notes/mem_alpha.md"
    assert alpha.keyword_rank is not None and alpha.semantic_rank is None
    assert alpha.reasons
    assert alpha.obsidian_uri.startswith("obsidian://open?vault=Global%20Memory")
    assert "recency_adjustment" in alpha.reasons
    assert page.project_source == "explicit" and page.project_explanation

    no_project = service.search(SearchRequest(query="conveyor", mode="keyword", limit=20))
    assert {result.memory_id for result in no_project.results} == {"mem_global", "mem_org"}


def test_explicit_cross_project_and_lifecycle_opt_ins(tmp_path: Path) -> None:
    database, indexer = fixture(tmp_path)
    service = SearchService(database, indexer)
    cross = service.search(
        SearchRequest(query="conveyor", project="Alpha", mode="keyword", cross_project=True, limit=20)
    )
    beta = next(result for result in cross.results if result.memory_id == "mem_beta")
    assert "cross_project" in beta.labels

    included = service.search(
        SearchRequest(
            query="conveyor",
            project="Alpha",
            mode="keyword",
            include_candidates=True,
            include_archived=True,
            include_rejected=True,
            include_superseded=True,
            limit=30,
        )
    )
    assert {"mem_candidate", "mem_archived", "mem_rejected", "mem_old"} <= {
        result.memory_id for result in included.results
    }
    assert "candidate" in next(result for result in included.results if result.memory_id == "mem_candidate").labels


class QueryProvider(FakeEmbeddingProvider):
    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [[1.0, 0.0] for _ in texts]


def test_hybrid_semantic_discovery_and_keyword_fallback(tmp_path: Path) -> None:
    database, indexer = fixture(tmp_path)
    vectors = FakeVectorStore()
    semantic_chunk = database.connection.execute(
        "SELECT c.id FROM chunks c WHERE c.document_id='mem_alpha'"
    ).fetchone()[0]
    vectors.upsert(semantic_chunk, "fake", "query", "hash", [1.0, 0.0])
    provider = QueryProvider(model="query", dimension=2)
    service = SearchService(database, indexer, embedding_provider=provider, vectors=vectors)

    semantic = service.search(SearchRequest(query="feeding machinery", project="Alpha", mode="hybrid"))
    assert semantic.results[0].memory_id == "mem_alpha"
    assert semantic.results[0].semantic_rank == 1

    unavailable = FakeEmbeddingProvider(model="down", dimension=2, available=False)
    degraded = SearchService(database, indexer, embedding_provider=unavailable, vectors=vectors).search(
        SearchRequest(query="conveyor", project="Alpha", mode="hybrid")
    )
    assert degraded.mode_used == "keyword"
    assert "semantic_unavailable_keyword_fallback" in degraded.warnings
    assert degraded.results

    with pytest.raises(GlobalMemoryError) as caught:
        SearchService(database, indexer, embedding_provider=unavailable, vectors=vectors).search(
            SearchRequest(query="conveyor", project="Alpha", mode="semantic")
        )
    assert caught.value.code is ErrorCode.EMBEDDING_PROVIDER_UNAVAILABLE


def test_cursor_is_keyset_based_stable_and_snapshot_bound(tmp_path: Path) -> None:
    database, indexer = fixture(tmp_path)
    service = SearchService(database, indexer)
    first = service.search(SearchRequest(query="conveyor", project="Alpha", mode="keyword", limit=2))
    assert first.next_cursor
    second = service.search(
        SearchRequest(query="conveyor", project="Alpha", mode="keyword", limit=2, cursor=first.next_cursor)
    )
    assert not ({item.memory_id for item in first.results} & {item.memory_id for item in second.results})

    database.connection.execute(
        "UPDATE documents SET indexed_at=? WHERE id='mem_alpha'", ((NOW + timedelta(days=1)).isoformat(),)
    )
    with pytest.raises(GlobalMemoryError) as caught:
        service.search(
            SearchRequest(query="conveyor", project="Alpha", mode="keyword", limit=2, cursor=first.next_cursor)
        )
    assert caught.value.code is ErrorCode.VERSION_CONFLICT


def test_context_is_diverse_bounded_sourced_and_labels_untrusted_text(tmp_path: Path) -> None:
    database, indexer = fixture(tmp_path)
    service = SearchService(database, indexer)
    bundle = ContextPacker(service).pack(task="conveyor", project="Alpha", token_budget=180)
    assert bundle.estimated_tokens <= 180
    assert len({item.type for item in bundle.items}) >= 2
    assert all(item.memory_id and item.path and item.content_is_untrusted for item in bundle.items)
    assert "UNTRUSTED STORED NOTE TEXT" in bundle.rendered_text
    assert "mem_alpha" in bundle.rendered_text


def test_metadata_mode_and_tag_filters_respect_project_scope(tmp_path: Path) -> None:
    database, indexer = fixture(tmp_path)
    service = SearchService(database, indexer)
    metadata = service.search(SearchRequest(query="alpha", project="Alpha", mode="metadata", limit=20))
    assert {result.memory_id for result in metadata.results} == {"mem_alpha", "mem_session"}
    tagged = service.search(SearchRequest(query="conveyor", project="Alpha", mode="keyword", tags=["alpha"], limit=20))
    assert {result.memory_id for result in tagged.results} == {"mem_alpha", "mem_session"}


def test_multiple_matching_chunks_group_into_one_document_result(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    write_note(
        vault,
        "mem_multi",
        "Multi passage",
        "# First\n\nconveyor alpha details\n\n# Second\n\nconveyor beta details\n",
        scope="global",
    )
    database = IndexDatabase(tmp_path / "data" / "memory.db")
    indexer = Indexer(vault, database, target_tokens=3, overlap_tokens=0)
    indexer.full_reindex()
    page = SearchService(database, indexer).search(SearchRequest(query="conveyor", mode="keyword"))
    assert len(page.results) == 1
    assert page.results[0].supporting_passages
    assert "active_status_adjustment" in page.results[0].reasons
