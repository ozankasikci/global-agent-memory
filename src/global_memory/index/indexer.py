"""Full and incremental Markdown-to-FTS indexing."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from global_memory.domain.models import ParsedMemory
from global_memory.errors import ErrorCode, GlobalMemoryError
from global_memory.index.chunks import TokenEstimator, approximate_tokens, chunk_markdown
from global_memory.index.database import IndexDatabase
from global_memory.vault.markdown import parse_note
from global_memory.vault.paths import is_managed_memory_path, safe_vault_path


@dataclass(frozen=True, slots=True)
class ReindexReport:
    indexed: int
    skipped: int
    invalid: int
    duplicate_ids: list[str]


@dataclass(frozen=True, slots=True)
class KeywordResult:
    chunk_id: str
    memory_id: str
    title: str
    path: str
    type: str
    scope: str
    project: str | None
    status: str
    excerpt: str
    heading_path: str | None
    keyword_rank: int
    updated_at: str


class Indexer:
    """Maintain a fully disposable keyword index from canonical Markdown."""

    def __init__(
        self,
        vault_path: Path,
        database: IndexDatabase,
        *,
        estimator: TokenEstimator = approximate_tokens,
        target_tokens: int = 550,
        overlap_tokens: int = 50,
    ) -> None:
        self.vault_path = vault_path
        self.database = database
        self.estimator = estimator
        self.target_tokens = target_tokens
        self.overlap_tokens = overlap_tokens

    def _files(self) -> list[Path]:
        return sorted(
            path for path in self.vault_path.rglob("*.md") if is_managed_memory_path(path.relative_to(self.vault_path))
        )

    def full_reindex(self) -> ReindexReport:
        parsed: list[tuple[Path, str, ParsedMemory]] = []
        invalid_paths: list[Path] = []
        for path in self._files():
            text = path.read_text()
            try:
                note = parse_note(text)
            except GlobalMemoryError:
                invalid_paths.append(path)
                continue
            parsed.append((path, text, note))
        by_id: dict[str, list[tuple[Path, str, ParsedMemory]]] = {}
        for item in parsed:
            by_id.setdefault(item[2].metadata.id, []).append(item)
        duplicates = sorted(memory_id for memory_id, items in by_id.items() if len(items) > 1)
        indexed = 0
        skipped = 0
        with self.database.transaction():
            self.database.connection.execute("DELETE FROM chunks_fts")
            self.database.connection.execute("DELETE FROM links")
            self.database.connection.execute("DELETE FROM chunks")
            self.database.connection.execute("DELETE FROM documents")
            for path in invalid_paths:
                self._event("full", path, "failed", ErrorCode.NOTE_INVALID.value, {})
            for memory_id, items in by_id.items():
                if len(items) > 1:
                    for path, _, _ in items:
                        self._event("full", path, "failed", ErrorCode.DUPLICATE_ID.value, {"id": memory_id})
                    continue
                path, text, note = items[0]
                self._upsert(path, text, note)
                indexed += 1
        return ReindexReport(indexed=indexed, skipped=skipped, invalid=len(invalid_paths), duplicate_ids=duplicates)

    def index_path(self, relative_path: Path) -> str:
        if not is_managed_memory_path(relative_path):
            return "ignored"
        path = safe_vault_path(self.vault_path, relative_path)
        if not path.exists():
            self.delete_path(relative_path)
            return "deleted"
        text = path.read_text()
        note = parse_note(text)
        existing = self.database.connection.execute(
            "SELECT path, content_hash FROM documents WHERE id = ?", (note.metadata.id,)
        ).fetchone()
        content_hash = hashlib.sha256(text.encode()).hexdigest()
        if existing and existing["path"] != relative_path.as_posix():
            old_file = self.vault_path / existing["path"]
            if old_file.exists():
                with self.database.transaction():
                    self._remove_search_rows(note.metadata.id)
                    self.database.connection.execute(
                        "UPDATE documents SET deleted_at = ? WHERE id = ?",
                        (datetime.now(UTC).isoformat(), note.metadata.id),
                    )
                    self._event("incremental", path, "failed", ErrorCode.DUPLICATE_ID.value, {"id": note.metadata.id})
                raise GlobalMemoryError(
                    ErrorCode.DUPLICATE_ID,
                    "A copied note duplicates an indexed immutable ID; neither copy remains searchable.",
                    details={"id": note.metadata.id, "paths": [existing["path"], relative_path.as_posix()]},
                    remediation="Resolve the duplicate explicitly and reindex the surviving note.",
                )
        if existing and existing["path"] == relative_path.as_posix() and existing["content_hash"] == content_hash:
            return "skipped"
        with self.database.transaction():
            self._upsert(path, text, note)
        return "indexed"

    def delete_path(self, relative_path: Path) -> None:
        safe_vault_path(self.vault_path, relative_path)
        row = self.database.connection.execute(
            "SELECT id FROM documents WHERE path = ? AND deleted_at IS NULL", (relative_path.as_posix(),)
        ).fetchone()
        if not row:
            return
        with self.database.transaction():
            self._remove_search_rows(row["id"])
            now = datetime.now(UTC).isoformat()
            self.database.connection.execute("UPDATE documents SET deleted_at = ? WHERE id = ?", (now, row["id"]))
            self._event("delete", self.vault_path / relative_path, "completed", None, {"id": row["id"]})

    def _remove_search_rows(self, memory_id: str) -> None:
        self.database.connection.execute(
            "DELETE FROM chunks_fts WHERE chunk_id IN (SELECT id FROM chunks WHERE document_id = ?)", (memory_id,)
        )
        self.database.connection.execute("DELETE FROM chunks WHERE document_id = ?", (memory_id,))
        self.database.connection.execute("DELETE FROM links WHERE source_document_id = ?", (memory_id,))

    def _upsert(self, path: Path, text: str, note: ParsedMemory) -> None:
        metadata = note.metadata
        relative = path.relative_to(self.vault_path).as_posix()
        now = datetime.now(UTC).isoformat()
        content_hash = hashlib.sha256(text.encode()).hexdigest()
        self._remove_search_rows(metadata.id)
        values = metadata.model_dump(mode="json")
        self.database.connection.execute(
            """
            INSERT INTO documents(
                id, path, title, type, scope, project, status, confidence, importance,
                created_at, updated_at, content_hash, metadata_json, indexed_at, deleted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
            ON CONFLICT(id) DO UPDATE SET
                path=excluded.path, title=excluded.title, type=excluded.type, scope=excluded.scope,
                project=excluded.project, status=excluded.status, confidence=excluded.confidence,
                importance=excluded.importance, created_at=excluded.created_at, updated_at=excluded.updated_at,
                content_hash=excluded.content_hash, metadata_json=excluded.metadata_json,
                indexed_at=excluded.indexed_at, deleted_at=NULL
            """,
            (
                metadata.id,
                relative,
                metadata.title,
                metadata.type,
                metadata.scope.value,
                metadata.project,
                metadata.status.value,
                metadata.confidence,
                metadata.importance,
                metadata.created_at.isoformat(),
                metadata.updated_at.isoformat(),
                content_hash,
                json.dumps(values, ensure_ascii=False, sort_keys=True),
                now,
            ),
        )
        chunks = chunk_markdown(
            metadata.title,
            note.body,
            estimator=self.estimator,
            target_tokens=self.target_tokens,
            overlap_tokens=self.overlap_tokens,
        )
        for chunk in chunks:
            chunk_id = hashlib.sha256(f"{metadata.id}:{chunk.ordinal}:{chunk.content_hash}".encode()).hexdigest()
            self.database.connection.execute(
                "INSERT INTO chunks VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    chunk_id,
                    metadata.id,
                    chunk.ordinal,
                    chunk.heading_path,
                    chunk.content,
                    chunk.content_hash,
                    chunk.estimated_tokens,
                ),
            )
            self.database.connection.execute(
                "INSERT INTO chunks_fts VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    chunk_id,
                    chunk.content,
                    metadata.title,
                    chunk.heading_path or "",
                    " ".join(metadata.tags),
                    metadata.project or "",
                    metadata.type,
                ),
            )
        for link in metadata.links:
            self.database.connection.execute(
                "INSERT INTO links(source_document_id, target_reference, target_document_id, link_kind) "
                "VALUES (?, ?, NULL, 'wikilink')",
                (metadata.id, link),
            )
        self._event("upsert", path, "completed", None, {"id": metadata.id, "chunks": len(chunks)})

    def keyword_search(
        self,
        query: str,
        *,
        project: str | None = None,
        scopes: list[str] | None = None,
        types: list[str] | None = None,
        statuses: list[str] | None = None,
        tags: list[str] | None = None,
        applicable_project: str | None = None,
        cross_project: bool = False,
        include_archive_scope: bool = False,
        apply_default_scope: bool = False,
        limit: int = 10,
    ) -> list[KeywordResult]:
        if re.fullmatch(r"mem_[A-Za-z0-9_-]+", query):
            return self.metadata_search(memory_id=query, project=project, scopes=scopes, types=types, statuses=statuses)
        tokens = re.findall(r"[\w-]+", query, flags=re.UNICODE)
        if not tokens:
            return []
        if len(query) >= 2 and query.startswith('"') and query.endswith('"'):
            phrase = query[1:-1].replace('"', '""')
            match = f'"{phrase}"'
        else:
            match = " AND ".join(f'"{token.replace(chr(34), chr(34) * 2)}"' for token in tokens)
        conditions = ["chunks_fts MATCH ?", "d.deleted_at IS NULL"]
        parameters: list[Any] = [match]
        if project is not None:
            conditions.append("d.project = ?")
            parameters.append(project)
        for column, selected in (("d.scope", scopes), ("d.type", types), ("d.status", statuses)):
            if selected:
                conditions.append(f"{column} IN ({','.join('?' for _ in selected)})")
                parameters.extend(selected)
        for tag in tags or []:
            conditions.append("EXISTS (SELECT 1 FROM json_each(d.metadata_json, '$.tags') WHERE value = ?)")
            parameters.append(tag)
        if not cross_project and (apply_default_scope or applicable_project is not None):
            shared = ["d.scope IN ('global', 'organization')"]
            if applicable_project is not None:
                shared.append("(d.scope = 'project' AND d.project = ?)")
                parameters.append(applicable_project)
            if include_archive_scope:
                shared.append("d.scope = 'archive'")
            conditions.append(f"({' OR '.join(shared)})")
        parameters.append(max(1, min(limit, 100)))
        rows = self.database.connection.execute(
            f"""
            SELECT d.*, c.id AS chunk_id, c.content, c.heading_path, bm25(chunks_fts) AS rank
            FROM chunks_fts
            JOIN chunks c ON c.id = chunks_fts.chunk_id
            JOIN documents d ON d.id = c.document_id
            WHERE {" AND ".join(conditions)}
            ORDER BY rank ASC, d.updated_at DESC, d.id ASC, c.ordinal ASC
            LIMIT ?
            """,
            parameters,
        ).fetchall()
        return [
            KeywordResult(
                chunk_id=row["chunk_id"],
                memory_id=row["id"],
                title=row["title"],
                path=row["path"],
                type=row["type"],
                scope=row["scope"],
                project=row["project"],
                status=row["status"],
                excerpt=row["content"][:500],
                heading_path=row["heading_path"],
                keyword_rank=rank,
                updated_at=row["updated_at"],
            )
            for rank, row in enumerate(rows, start=1)
        ]

    def metadata_search(
        self,
        *,
        memory_id: str | None = None,
        project: str | None = None,
        scopes: list[str] | None = None,
        types: list[str] | None = None,
        statuses: list[str] | None = None,
        tags: list[str] | None = None,
        limit: int = 10,
    ) -> list[KeywordResult]:
        """Retrieve from normalized metadata without requiring FTS terms."""
        conditions = ["d.deleted_at IS NULL", "c.ordinal = 0"]
        parameters: list[Any] = []
        if memory_id is not None:
            conditions.append("d.id = ?")
            parameters.append(memory_id)
        if project is not None:
            conditions.append("d.project = ?")
            parameters.append(project)
        for column, selected in (("d.scope", scopes), ("d.type", types), ("d.status", statuses)):
            if selected:
                conditions.append(f"{column} IN ({','.join('?' for _ in selected)})")
                parameters.extend(selected)
        for tag in tags or []:
            conditions.append("EXISTS (SELECT 1 FROM json_each(d.metadata_json, '$.tags') WHERE value = ?)")
            parameters.append(tag)
        parameters.append(max(1, min(limit, 100)))
        rows = self.database.connection.execute(
            f"""
            SELECT d.*, c.id AS chunk_id, c.content, c.heading_path
            FROM documents d
            JOIN chunks c ON c.document_id = d.id
            WHERE {" AND ".join(conditions)}
            ORDER BY d.updated_at DESC, d.id ASC
            LIMIT ?
            """,
            parameters,
        ).fetchall()
        return [
            KeywordResult(
                chunk_id=row["chunk_id"],
                memory_id=row["id"],
                title=row["title"],
                path=row["path"],
                type=row["type"],
                scope=row["scope"],
                project=row["project"],
                status=row["status"],
                excerpt=row["content"][:500],
                heading_path=row["heading_path"],
                keyword_rank=rank,
                updated_at=row["updated_at"],
            )
            for rank, row in enumerate(rows, start=1)
        ]

    def _event(
        self,
        operation: str,
        path: Path,
        status: str,
        error_code: str | None,
        details: dict[str, Any],
    ) -> None:
        relative = path.relative_to(self.vault_path).as_posix()
        self.database.connection.execute(
            "INSERT INTO index_events(operation, path, status, error_code, details_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                operation,
                relative,
                status,
                error_code,
                json.dumps(details, sort_keys=True),
                datetime.now(UTC).isoformat(),
            ),
        )
