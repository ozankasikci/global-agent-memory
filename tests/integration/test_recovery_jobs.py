from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from global_memory.application.memory_service import MemoryService
from global_memory.domain.models import MemoryDraft
from global_memory.index.database import IndexDatabase, open_recoverable_database
from global_memory.index.indexer import Indexer
from global_memory.index.jobs import IndexJobQueue
from global_memory.vault.repository import VaultRepository

pytestmark = pytest.mark.integration
NOW = datetime(2026, 7, 11, 12, 0, tzinfo=UTC)


def _memory(tmp_path: Path):
    repository = VaultRepository(tmp_path / "vault", tmp_path / "data/audit.jsonl", clock=lambda: NOW)
    return MemoryService(repository).remember(
        MemoryDraft(
            title="Recovery",
            content="# Recovery\n\nOriginal durable body.\n",
            type="fact",
            scope="global",
        )
    )


def _queue(tmp_path: Path) -> tuple[IndexDatabase, Indexer, IndexJobQueue]:
    database = IndexDatabase(tmp_path / "data/memory.db")
    indexer = Indexer(tmp_path / "vault", database)
    jobs = IndexJobQueue(database, indexer)
    return database, indexer, jobs


def test_rapid_saves_coalesce_and_index_latest_file(tmp_path: Path) -> None:
    memory = _memory(tmp_path)
    database, indexer, jobs = _queue(tmp_path)
    jobs.reconcile()
    jobs.process_due()

    for revision in ("First", "Second", "Final"):
        memory.path.write_text(memory.path.read_text().replace("Original", revision))
        jobs.enqueue(memory.relative_path)
        if revision != "Final":
            memory.path.write_text(memory.path.read_text().replace(revision, "Original"))
    assert (
        database.connection.execute(
            "SELECT COUNT(*) FROM index_jobs WHERE path=? AND status='pending'", (memory.relative_path.as_posix(),)
        ).fetchone()[0]
        == 1
    )

    assert jobs.process_due().completed == 1
    assert indexer.keyword_search("Final")[0].memory_id == memory.metadata.id


def test_startup_reconciliation_recovers_a_crash_after_markdown_write(tmp_path: Path) -> None:
    memory = _memory(tmp_path)
    _, indexer, jobs = _queue(tmp_path)
    jobs.reconcile()
    jobs.process_due()
    memory.path.write_text(memory.path.read_text().replace("Original", "Recovered-after-crash"))

    restarted_jobs = IndexJobQueue(jobs.database, indexer)
    assert restarted_jobs.reconcile() == 1
    assert restarted_jobs.process_due().completed == 1
    assert indexer.keyword_search("Recovered-after-crash")


def test_invalid_and_duplicate_notes_are_isolated_as_terminal_jobs(tmp_path: Path) -> None:
    memory = _memory(tmp_path)
    database, indexer, jobs = _queue(tmp_path)
    jobs.reconcile()
    jobs.process_due()
    invalid = tmp_path / "vault/10 Global/invalid.md"
    invalid.parent.mkdir(parents=True, exist_ok=True)
    invalid.write_text("# invalid\n")
    jobs.enqueue(invalid.relative_to(tmp_path / "vault"))
    assert jobs.process_due().failed == 1

    duplicate = tmp_path / "vault/10 Global/duplicate.md"
    shutil.copy2(memory.path, duplicate)
    jobs.enqueue(duplicate.relative_to(tmp_path / "vault"))
    assert jobs.process_due().failed == 1
    failures = database.connection.execute(
        "SELECT last_error FROM index_jobs WHERE status='failed' ORDER BY path"
    ).fetchall()
    assert {row[0] for row in failures} == {"NOTE_INVALID", "DUPLICATE_ID"}
    assert not indexer.keyword_search("Original")


def test_corrupt_or_deleted_database_rebuilds_from_markdown(tmp_path: Path) -> None:
    memory = _memory(tmp_path)
    database_path = tmp_path / "data/memory.db"
    database_path.parent.mkdir(parents=True, exist_ok=True)
    database_path.write_bytes(b"not a sqlite database")

    opened = open_recoverable_database(database_path)
    assert opened.recovered_from and opened.recovered_from.read_bytes() == b"not a sqlite database"
    indexer = Indexer(tmp_path / "vault", opened.database)
    jobs = IndexJobQueue(opened.database, indexer)
    assert jobs.reconcile() == 1
    jobs.process_due()
    assert indexer.keyword_search("Original")[0].memory_id == memory.metadata.id

    opened.database.close()
    database_path.unlink()
    rebuilt = open_recoverable_database(database_path).database
    rebuilt_indexer = Indexer(tmp_path / "vault", rebuilt)
    rebuilt_jobs = IndexJobQueue(rebuilt, rebuilt_indexer)
    rebuilt_jobs.reconcile()
    rebuilt_jobs.process_due()
    assert rebuilt_indexer.keyword_search("Original")
