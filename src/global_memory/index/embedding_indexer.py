"""Changed-only embedding work with persisted retry diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from global_memory.embeddings.base import EmbeddingProvider
from global_memory.errors import GlobalMemoryError
from global_memory.index.database import IndexDatabase
from global_memory.index.vectors import VectorStore


@dataclass(frozen=True, slots=True)
class EmbeddingReport:
    embedded: int
    skipped: int
    failed: int
    keyword_only: bool


class EmbeddingIndexer:
    def __init__(self, database: IndexDatabase, vectors: VectorStore) -> None:
        self.database = database
        self.vectors = vectors

    def _pending(self, chunk_id: str, provider: EmbeddingProvider, content_hash: str, error: str) -> None:
        now = datetime.now(UTC).isoformat()
        with self.database.transaction():
            self.database.connection.execute(
                """
                INSERT INTO embedding_jobs(
                    chunk_id, provider, model, content_hash, status, attempts, last_error, updated_at
                )
                VALUES (?, ?, ?, ?, 'pending', 1, ?, ?)
                ON CONFLICT(chunk_id) DO UPDATE SET provider=excluded.provider, model=excluded.model,
                    content_hash=excluded.content_hash, status='pending', attempts=embedding_jobs.attempts + 1,
                    last_error=excluded.last_error, updated_at=excluded.updated_at
                """,
                (chunk_id, provider.provider, provider.model, content_hash, error, now),
            )

    def sync(self, provider: EmbeddingProvider, *, batch_size: int = 32) -> EmbeddingReport:
        chunks = self.database.connection.execute(
            "SELECT c.id, c.content, c.content_hash FROM chunks c JOIN documents d ON d.id=c.document_id "
            "WHERE d.deleted_at IS NULL ORDER BY c.id"
        ).fetchall()
        self.vectors.prune({str(chunk["id"]) for chunk in chunks})
        pending = []
        skipped = 0
        for chunk in chunks:
            existing = self.database.connection.execute(
                "SELECT dimension FROM embeddings WHERE chunk_id=? AND provider=? AND model=? AND content_hash=?",
                (chunk["id"], provider.provider, provider.model, chunk["content_hash"]),
            ).fetchone()
            if existing and (provider.dimension is None or existing["dimension"] == provider.dimension):
                skipped += 1
            else:
                pending.append(chunk)
        embedded = 0
        failed = 0
        for start in range(0, len(pending), batch_size):
            batch = pending[start : start + batch_size]
            try:
                vectors = provider.embed([row["content"] for row in batch])
                if len(vectors) != len(batch):
                    raise ValueError("embedding count mismatch")
                for row, vector in zip(batch, vectors, strict=True):
                    self.vectors.upsert(row["id"], provider.provider, provider.model, row["content_hash"], vector)
                    self.vectors.delete_other_models(row["id"], provider.provider, provider.model)
                    self.database.connection.execute("DELETE FROM embedding_jobs WHERE chunk_id=?", (row["id"],))
                    embedded += 1
            except (GlobalMemoryError, ValueError) as exc:
                for row in batch:
                    self._pending(row["id"], provider, row["content_hash"], type(exc).__name__)
                    failed += 1
        return EmbeddingReport(
            embedded=embedded,
            skipped=skipped,
            failed=failed,
            keyword_only=failed > 0 or not self.vectors.available,
        )
