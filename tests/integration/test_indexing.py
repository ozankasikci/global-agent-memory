from __future__ import annotations

import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from global_memory.application.memory_service import MemoryService
from global_memory.domain.models import MemoryDraft
from global_memory.errors import ErrorCode, GlobalMemoryError
from global_memory.index.database import IndexDatabase
from global_memory.index.indexer import Indexer
from global_memory.vault.obsidian import ensure_project_overview, install_obsidian_assets
from global_memory.vault.repository import VaultRepository

pytestmark = pytest.mark.integration
NOW = datetime(2026, 7, 11, 10, 0, tzinfo=UTC)


def active_note(
    tmp_path: Path, *, title: str = "FTS decision", content: str = "Exact VERSION_CONFLICT recovery 日本語"
):
    repo = VaultRepository(tmp_path / "vault", tmp_path / "data" / "audit.jsonl", clock=lambda: NOW)
    candidate = MemoryService(repo).remember(
        MemoryDraft(
            title=title,
            content=content,
            type="decision",
            scope="project",
            project="Global Memory",
            tags=["sqlite", "search"],
        )
    )
    later = VaultRepository(
        tmp_path / "vault", tmp_path / "data" / "audit.jsonl", clock=lambda: NOW + timedelta(seconds=1)
    )
    return MemoryService(later).approve(candidate.metadata.id, candidate.version)


def test_migrations_wal_full_index_filters_and_rebuild_equivalence(tmp_path: Path) -> None:
    note = active_note(tmp_path)
    database = IndexDatabase(tmp_path / "data" / "memory.db")
    indexer = Indexer(tmp_path / "vault", database)

    report = indexer.full_reindex()
    before = indexer.keyword_search("VERSION_CONFLICT", project="Global Memory", statuses=["active"])
    assert report.indexed == 1
    assert [result.memory_id for result in before] == [note.metadata.id]
    assert before[0].path == note.relative_path.as_posix()
    assert indexer.keyword_search("日本語")[0].memory_id == note.metadata.id
    assert indexer.keyword_search(note.metadata.id)[0].memory_id == note.metadata.id
    assert indexer.keyword_search('"Exact VERSION_CONFLICT"')[0].memory_id == note.metadata.id
    assert indexer.keyword_search("Handle Exact VERSION_CONFLICT safely")[0].memory_id == note.metadata.id
    assert not indexer.keyword_search('"missing VERSION_CONFLICT"')
    assert indexer.metadata_search(project="Global Memory", types=["decision"], tags=["sqlite"])[0].memory_id == (
        note.metadata.id
    )
    assert database.connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert database.connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert database.connection.execute("SELECT version FROM schema_migrations").fetchall()

    indexer.full_reindex()
    after = indexer.keyword_search("VERSION_CONFLICT", project="Global Memory", statuses=["active"])
    assert [(item.memory_id, item.path, item.excerpt) for item in after] == [
        (item.memory_id, item.path, item.excerpt) for item in before
    ]


def test_incremental_edit_move_and_delete(tmp_path: Path) -> None:
    note = active_note(tmp_path)
    database = IndexDatabase(tmp_path / "data" / "memory.db")
    indexer = Indexer(tmp_path / "vault", database)
    indexer.full_reindex()

    edited = note.path.read_text().replace("recovery", "reconciliation")
    note.path.write_text(edited)
    assert indexer.index_path(note.relative_path) == "indexed"
    assert indexer.keyword_search("reconciliation")

    moved = Path("20 Projects/Global Memory/Decisions/Renamed.md")
    destination = tmp_path / "vault" / moved
    destination.parent.mkdir(parents=True, exist_ok=True)
    note.path.rename(destination)
    assert indexer.index_path(moved) == "indexed"
    assert indexer.keyword_search("reconciliation")[0].path == moved.as_posix()

    destination.unlink()
    indexer.delete_path(moved)
    assert not indexer.keyword_search("reconciliation")
    assert database.connection.execute("SELECT deleted_at FROM documents WHERE id = ?", (note.metadata.id,)).fetchone()[
        0
    ]


def test_duplicate_ids_quarantine_both_copies(tmp_path: Path) -> None:
    note = active_note(tmp_path)
    copy = tmp_path / "vault" / "10 Global" / "copy.md"
    copy.parent.mkdir(parents=True)
    shutil.copy2(note.path, copy)
    indexer = Indexer(tmp_path / "vault", IndexDatabase(tmp_path / "data" / "memory.db"))

    report = indexer.full_reindex()

    assert report.duplicate_ids == [note.metadata.id]
    assert not indexer.keyword_search("VERSION_CONFLICT")


def test_incremental_copy_returns_stable_duplicate_error(tmp_path: Path) -> None:
    note = active_note(tmp_path)
    indexer = Indexer(tmp_path / "vault", IndexDatabase(tmp_path / "data" / "memory.db"))
    indexer.full_reindex()
    copy = tmp_path / "vault" / "10 Global" / "copy.md"
    copy.parent.mkdir(parents=True)
    shutil.copy2(note.path, copy)

    with pytest.raises(GlobalMemoryError) as caught:
        indexer.index_path(copy.relative_to(tmp_path / "vault"))
    assert caught.value.code is ErrorCode.DUPLICATE_ID
    assert not indexer.keyword_search("VERSION_CONFLICT")


def test_invalid_notes_are_isolated_and_recorded(tmp_path: Path) -> None:
    active_note(tmp_path)
    invalid = tmp_path / "vault" / "broken.md"
    invalid.write_text("# missing managed frontmatter\n")
    database = IndexDatabase(tmp_path / "data" / "memory.db")
    report = Indexer(tmp_path / "vault", database).full_reindex()
    assert report.invalid == 1
    event = database.connection.execute(
        "SELECT status, error_code FROM index_events WHERE path = 'broken.md' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert tuple(event) == ("failed", ErrorCode.NOTE_INVALID.value)


def test_obsidian_support_assets_are_not_reported_as_invalid_memories(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "README.md").write_text("# Global Memory\n")
    install_obsidian_assets(vault)
    ensure_project_overview(vault, "Global Memory")

    report = Indexer(vault, IndexDatabase(tmp_path / "data" / "memory.db")).full_reindex()

    assert report.invalid == 0
