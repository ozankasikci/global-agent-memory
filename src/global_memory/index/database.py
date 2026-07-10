"""SQLite connection ownership and forward-only generated-state migrations."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
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


class IndexDatabase:
    """Own one generated SQLite database with mandatory safety pragmas."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, isolation_level=None)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA foreign_keys=ON")
        self._migrate()

    def _migrate(self) -> None:
        current = self.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
        ).fetchone()
        version = 0
        if current:
            row = self.connection.execute("SELECT COALESCE(MAX(version), 0) FROM schema_migrations").fetchone()
            version = int(row[0])
        if version < 1:
            self.connection.executescript(
                "BEGIN IMMEDIATE;\n"
                + MIGRATION_1
                + "\nINSERT INTO schema_migrations(version, applied_at) VALUES (1, datetime('now'));\nCOMMIT;"
            )

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
