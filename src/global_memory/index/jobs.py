"""Persisted filesystem indexing jobs and startup reconciliation."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from global_memory.errors import ErrorCode, GlobalMemoryError
from global_memory.index.database import IndexDatabase
from global_memory.index.indexer import Indexer
from global_memory.vault.paths import is_managed_memory_path


@dataclass(frozen=True, slots=True)
class JobReport:
    completed: int
    retried: int
    failed: int


class IndexJobQueue:
    """Durable at-least-once jobs; indexing operations themselves are idempotent."""

    def __init__(
        self,
        database: IndexDatabase,
        indexer: Indexer,
        *,
        max_attempts: int = 5,
        on_indexed: Callable[[Path], None] | None = None,
    ) -> None:
        self.database = database
        self.indexer = indexer
        self.max_attempts = max_attempts
        self.on_indexed = on_indexed

    def enqueue(self, relative_path: Path, event_type: str = "upsert") -> bool:
        if not is_managed_memory_path(relative_path):
            return False
        now = datetime.now(UTC).isoformat()
        self.database.connection.execute(
            """
            INSERT INTO index_jobs(path, event_type, status, attempts, last_error, next_attempt_at, updated_at)
            VALUES (?, ?, 'pending', 0, NULL, NULL, ?)
            ON CONFLICT(path) DO UPDATE SET event_type=excluded.event_type, status='pending', attempts=0,
                last_error=NULL, next_attempt_at=NULL, updated_at=excluded.updated_at
            """,
            (relative_path.as_posix(), event_type, now),
        )
        return True

    def reconcile(self) -> int:
        """Queue every new/changed file and every indexed path missing on disk."""
        disk: dict[str, str] = {}
        for file_path in sorted(self.indexer.vault_path.rglob("*.md")):
            relative = file_path.relative_to(self.indexer.vault_path)
            if is_managed_memory_path(relative):
                disk[relative.as_posix()] = hashlib.sha256(file_path.read_bytes()).hexdigest()
        rows = self.database.connection.execute(
            "SELECT path, content_hash FROM documents WHERE deleted_at IS NULL"
        ).fetchall()
        indexed = {str(row["path"]): str(row["content_hash"]) for row in rows}
        queued = 0
        for path_text, content_hash in disk.items():
            if indexed.get(path_text) != content_hash:
                queued += int(self.enqueue(Path(path_text), "upsert"))
        for path_text in indexed.keys() - disk.keys():
            queued += int(self.enqueue(Path(path_text), "delete"))
        return queued

    def process_due(self, *, now: datetime | None = None) -> JobReport:
        current = now or datetime.now(UTC)
        rows = self.database.connection.execute(
            """
            SELECT * FROM index_jobs
            WHERE status='pending' AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
            ORDER BY updated_at, path
            """,
            (current.isoformat(),),
        ).fetchall()
        completed = retried = failed = 0
        for row in rows:
            path = Path(row["path"])
            try:
                if row["event_type"] == "delete" or not (self.indexer.vault_path / path).exists():
                    self.indexer.delete_path(path)
                else:
                    self.indexer.index_path(path)
            except GlobalMemoryError as exc:
                terminal = exc.code in {ErrorCode.NOTE_INVALID, ErrorCode.DUPLICATE_ID}
                completed_state = "failed" if terminal else "pending"
                attempts = int(row["attempts"]) + 1
                if attempts >= self.max_attempts:
                    terminal = True
                    completed_state = "failed"
                delay = min(2 ** max(0, attempts - 1), 300)
                self.database.connection.execute(
                    "UPDATE index_jobs SET status=?, attempts=?, last_error=?, next_attempt_at=?, updated_at=? "
                    "WHERE path=?",
                    (
                        completed_state,
                        attempts,
                        exc.code.value,
                        None if terminal else (current + timedelta(seconds=delay)).isoformat(),
                        current.isoformat(),
                        path.as_posix(),
                    ),
                )
                if terminal:
                    failed += 1
                else:
                    retried += 1
            except OSError:
                attempts = int(row["attempts"]) + 1
                terminal = attempts >= self.max_attempts
                delay = min(2 ** max(0, attempts - 1), 300)
                self.database.connection.execute(
                    "UPDATE index_jobs SET status=?, attempts=?, last_error='IO_ERROR', next_attempt_at=?, "
                    "updated_at=? WHERE path=?",
                    (
                        "failed" if terminal else "pending",
                        attempts,
                        None if terminal else (current + timedelta(seconds=delay)).isoformat(),
                        current.isoformat(),
                        path.as_posix(),
                    ),
                )
                failed += int(terminal)
                retried += int(not terminal)
            else:
                if row["event_type"] != "delete" and self.on_indexed is not None:
                    self.on_indexed(path)
                self.database.connection.execute(
                    "UPDATE index_jobs SET status='completed', last_error=NULL, next_attempt_at=NULL, updated_at=? "
                    "WHERE path=?",
                    (current.isoformat(), path.as_posix()),
                )
                completed += 1
        return JobReport(completed=completed, retried=retried, failed=failed)
