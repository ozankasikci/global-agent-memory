"""SQLite connection ownership and forward-only generated-state migrations."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

MIGRATION_1 = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    path TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    type TEXT NOT NULL,
    scope TEXT NOT NULL,
    project TEXT NULL,
    status TEXT NOT NULL,
    confidence REAL NOT NULL,
    importance REAL NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    indexed_at TEXT NOT NULL,
    deleted_at TEXT NULL
);
CREATE TABLE IF NOT EXISTS chunks (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL,
    heading_path TEXT NULL,
    content TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    estimated_tokens INTEGER NOT NULL,
    UNIQUE(document_id, ordinal)
);
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    chunk_id UNINDEXED,
    content,
    title,
    heading_path,
    tags,
    project,
    type,
    tokenize='unicode61'
);
CREATE TABLE IF NOT EXISTS links (
    source_document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    target_reference TEXT NOT NULL,
    target_document_id TEXT NULL,
    link_kind TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS embeddings (
    chunk_id TEXT NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    dimension INTEGER NOT NULL,
    content_hash TEXT NOT NULL,
    PRIMARY KEY(chunk_id, provider, model)
);
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    canonical_name TEXT UNIQUE NOT NULL,
    aliases_json TEXT NOT NULL,
    roots_json TEXT NOT NULL,
    git_remotes_json TEXT NOT NULL,
    organization TEXT NULL,
    active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS index_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation TEXT NOT NULL,
    path TEXT NULL,
    status TEXT NOT NULL,
    error_code TEXT NULL,
    details_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS mutation_requests (
    request_id TEXT PRIMARY KEY,
    operation TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    result_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""

MIGRATION_2 = """
CREATE TABLE IF NOT EXISTS embedding_jobs (
    chunk_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    status TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT NULL,
    next_attempt_at TEXT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(chunk_id) REFERENCES chunks(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS vector_entries (
    row_id INTEGER PRIMARY KEY AUTOINCREMENT,
    chunk_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    dimension INTEGER NOT NULL,
    content_hash TEXT NOT NULL,
    collection_key TEXT NOT NULL,
    UNIQUE(chunk_id, provider, model)
);
CREATE INDEX IF NOT EXISTS vector_entries_collection ON vector_entries(collection_key, row_id);
"""

MIGRATION_3 = """
CREATE TABLE IF NOT EXISTS index_jobs (
    path TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    status TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT NULL,
    next_attempt_at TEXT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS index_jobs_due ON index_jobs(status, next_attempt_at);
"""

MIGRATION_4 = """
ALTER TABLE documents ADD COLUMN visibility TEXT NOT NULL DEFAULT 'standard';
CREATE INDEX IF NOT EXISTS documents_visibility ON documents(visibility, status, project);
CREATE TABLE IF NOT EXISTS access_requests (
    id TEXT PRIMARY KEY,
    agent TEXT NOT NULL,
    project TEXT NULL,
    purpose TEXT NOT NULL,
    permission TEXT NOT NULL,
    requested_duration TEXT NOT NULL,
    query TEXT NOT NULL,
    matched_ids_json TEXT NOT NULL,
    sealed_match_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    resolved_at TEXT NULL,
    resolution_note TEXT NULL
);
CREATE INDEX IF NOT EXISTS access_requests_status ON access_requests(status, created_at);
CREATE TABLE IF NOT EXISTS access_grants (
    id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL REFERENCES access_requests(id),
    agent TEXT NOT NULL,
    project TEXT NULL,
    purpose TEXT NOT NULL,
    permission TEXT NOT NULL,
    scope_ids_json TEXT NOT NULL,
    duration TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NULL,
    remaining_uses INTEGER NULL
);
CREATE INDEX IF NOT EXISTS access_grants_status ON access_grants(status, expires_at);
CREATE TABLE IF NOT EXISTS access_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id TEXT NULL,
    grant_id TEXT NULL,
    agent TEXT NOT NULL,
    action TEXT NOT NULL,
    purpose TEXT NOT NULL,
    permission TEXT NOT NULL,
    scope TEXT NOT NULL,
    actor TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS access_events_created ON access_events(created_at DESC);
"""


def _sql_statements(script: str) -> Iterator[str]:
    """Yield complete SQLite statements so migrations can share one outer lock."""
    buffered = ""
    for line in script.splitlines():
        buffered += line + "\n"
        if sqlite3.complete_statement(buffered):
            statement = buffered.strip()
            if statement:
                yield statement
            buffered = ""
    if buffered.strip():
        raise sqlite3.DatabaseError("migration contains an incomplete SQL statement")


@dataclass(frozen=True, slots=True)
class DatabaseOpenResult:
    database: IndexDatabase
    recovered_from: Path | None


class IndexDatabase:
    """Own one generated SQLite database with mandatory safety pragmas."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, isolation_level=None, timeout=30)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA busy_timeout=30000")
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA foreign_keys=ON")
        self._migrate()

    def _migrate(self) -> None:
        migrations = ((1, MIGRATION_1), (2, MIGRATION_2), (3, MIGRATION_3), (4, MIGRATION_4))
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            self.connection.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            row = self.connection.execute("SELECT COALESCE(MAX(version), 0) FROM schema_migrations").fetchone()
            version = int(row[0])
            for target, script in migrations:
                if version >= target:
                    continue
                for statement in _sql_statements(script):
                    self.connection.execute(statement)
                self.connection.execute(
                    "INSERT INTO schema_migrations(version, applied_at) VALUES (?, datetime('now'))",
                    (target,),
                )
                version = target
        except BaseException:
            self.connection.execute("ROLLBACK")
            raise
        else:
            self.connection.execute("COMMIT")

    @contextmanager
    def transaction(self) -> Iterator[None]:
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self.connection.execute("ROLLBACK")
            raise
        else:
            self.connection.execute("COMMIT")

    def integrity_check(self) -> bool:
        result = self.connection.execute("PRAGMA integrity_check").fetchone()
        return str(result[0]) == "ok"

    def close(self) -> None:
        self.connection.close()

    def __del__(self) -> None:
        connection = getattr(self, "connection", None)
        if connection is not None:
            with suppress(sqlite3.Error):
                connection.close()


def open_recoverable_database(path: Path) -> DatabaseOpenResult:
    """Open generated state, quarantining corruption so Markdown can rebuild it."""
    database: IndexDatabase | None = None
    try:
        database = IndexDatabase(path)
        if not database.integrity_check():
            raise sqlite3.DatabaseError("integrity_check failed")
        return DatabaseOpenResult(database=database, recovered_from=None)
    except sqlite3.DatabaseError:
        if database is not None:
            database.close()
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        quarantined = path.with_name(f"{path.name}.corrupt-{stamp}")
        if path.exists():
            path.replace(quarantined)
        for suffix in ("-wal", "-shm"):
            path.with_name(path.name + suffix).unlink(missing_ok=True)
        rebuilt = IndexDatabase(path)
        return DatabaseOpenResult(database=rebuilt, recovered_from=quarantined if quarantined.exists() else None)
