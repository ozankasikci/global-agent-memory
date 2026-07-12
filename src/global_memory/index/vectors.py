"""Replaceable vector stores, including the preferred sqlite-vec adapter."""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from typing import Protocol, cast

from global_memory.errors import ErrorCode, GlobalMemoryError
from global_memory.index.database import IndexDatabase


@dataclass(frozen=True, slots=True)
class VectorMatch:
    chunk_id: str
    distance: float


class VectorStore(Protocol):
    available: bool

    def upsert(self, chunk_id: str, provider: str, model: str, content_hash: str, vector: list[float]) -> bool: ...

    def search(self, provider: str, model: str, vector: list[float], *, limit: int) -> list[VectorMatch]: ...

    def delete_other_models(self, chunk_id: str, provider: str, model: str) -> None: ...

    def prune(self, valid_chunk_ids: set[str]) -> None: ...


class _SqliteVecModule(Protocol):
    def serialize_float32(self, vector: list[float]) -> bytes: ...


class FakeVectorStore:
    def __init__(self, *, available: bool = True) -> None:
        self.available = available
        self.values: dict[tuple[str, str, str], tuple[str, list[float]]] = {}

    def _require(self) -> None:
        if not self.available:
            raise GlobalMemoryError(ErrorCode.VECTOR_INDEX_UNAVAILABLE, "The vector index is unavailable.")

    def upsert(self, chunk_id: str, provider: str, model: str, content_hash: str, vector: list[float]) -> bool:
        self._require()
        key = (chunk_id, provider, model)
        if self.values.get(key) == (content_hash, vector):
            return False
        self.values[key] = (content_hash, list(vector))
        return True

    def search(self, provider: str, model: str, vector: list[float], *, limit: int) -> list[VectorMatch]:
        self._require()

        def distance(candidate: list[float]) -> float:
            dot = sum(left * right for left, right in zip(candidate, vector, strict=True))
            magnitudes = math.sqrt(sum(value * value for value in candidate)) * math.sqrt(
                sum(value * value for value in vector)
            )
            return 1.0 - (dot / magnitudes if magnitudes else 0.0)

        matches = [
            VectorMatch(chunk_id=chunk_id, distance=distance(candidate))
            for (chunk_id, stored_provider, stored_model), (_, candidate) in self.values.items()
            if stored_provider == provider and stored_model == model
        ]
        return sorted(matches, key=lambda match: (match.distance, match.chunk_id))[:limit]

    def delete_other_models(self, chunk_id: str, provider: str, model: str) -> None:
        for key in list(self.values):
            if key[0] == chunk_id and key[1] == provider and key[2] != model:
                del self.values[key]

    def prune(self, valid_chunk_ids: set[str]) -> None:
        for key in list(self.values):
            if key[0] not in valid_chunk_ids:
                del self.values[key]


class SqliteVecStore:
    """Store cosine vectors in dimension-specific sqlite-vec virtual tables."""

    def __init__(self, database: IndexDatabase) -> None:
        self.database = database
        self.available = False
        self._sqlite_vec: _SqliteVecModule | None = None
        try:
            import sqlite_vec  # type: ignore[import-untyped]

            database.connection.enable_load_extension(True)
            sqlite_vec.load(database.connection)
            database.connection.enable_load_extension(False)
            self._sqlite_vec = cast(_SqliteVecModule, sqlite_vec)
            self.available = True
        except (ImportError, AttributeError, OSError):
            self.available = False

    def _require(self) -> None:
        if not self.available or self._sqlite_vec is None:
            raise GlobalMemoryError(
                ErrorCode.VECTOR_INDEX_UNAVAILABLE,
                "The sqlite-vec extension is unavailable.",
                retryable=False,
                remediation="Install a compatible sqlite-vec build or use keyword-only mode.",
            )

    @staticmethod
    def _collection(provider: str, model: str, dimension: int) -> tuple[str, str]:
        key = hashlib.sha256(f"{provider}:{model}:{dimension}".encode()).hexdigest()[:20]
        return key, f"vec_{key}"

    @staticmethod
    def _table(value: str) -> str:
        if not re.fullmatch(r"vec_[0-9a-f]{20}", value):
            raise ValueError("invalid generated vector table name")
        return value

    def upsert(self, chunk_id: str, provider: str, model: str, content_hash: str, vector: list[float]) -> bool:
        self._require()
        dimension = len(vector)
        key, raw_table = self._collection(provider, model, dimension)
        table = self._table(raw_table)
        existing = self.database.connection.execute(
            "SELECT * FROM vector_entries WHERE chunk_id=? AND provider=? AND model=?",
            (chunk_id, provider, model),
        ).fetchone()
        if existing and existing["content_hash"] == content_hash and existing["dimension"] == dimension:
            return False
        sqlite_vec = self._sqlite_vec
        assert sqlite_vec is not None
        serialize = sqlite_vec.serialize_float32
        with self.database.transaction():
            self.database.connection.execute(
                f"CREATE VIRTUAL TABLE IF NOT EXISTS {table} "
                f"USING vec0(embedding float[{dimension}] distance_metric=cosine)"
            )
            if existing:
                old_table = self._table(f"vec_{existing['collection_key']}")
                self.database.connection.execute(f"DELETE FROM {old_table} WHERE rowid = ?", (existing["row_id"],))
                self.database.connection.execute("DELETE FROM vector_entries WHERE row_id = ?", (existing["row_id"],))
                self.database.connection.execute(
                    "DELETE FROM embeddings WHERE chunk_id=? AND provider=? AND model=?", (chunk_id, provider, model)
                )
            cursor = self.database.connection.execute(
                "INSERT INTO vector_entries(chunk_id, provider, model, dimension, content_hash, collection_key) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (chunk_id, provider, model, dimension, content_hash, key),
            )
            if cursor.lastrowid is None:
                raise RuntimeError("SQLite did not assign a vector row ID")
            row_id = cursor.lastrowid
            self.database.connection.execute(
                f"INSERT INTO {table}(rowid, embedding) VALUES (?, ?)", (row_id, serialize(vector))
            )
            self.database.connection.execute(
                "INSERT INTO embeddings(chunk_id, provider, model, dimension, content_hash) VALUES (?, ?, ?, ?, ?)",
                (chunk_id, provider, model, dimension, content_hash),
            )
        return True

    def search(self, provider: str, model: str, vector: list[float], *, limit: int) -> list[VectorMatch]:
        self._require()
        key, raw_table = self._collection(provider, model, len(vector))
        table = self._table(raw_table)
        exists = self.database.connection.execute(
            "SELECT 1 FROM vector_entries WHERE collection_key = ? LIMIT 1", (key,)
        ).fetchone()
        if not exists:
            return []
        sqlite_vec = self._sqlite_vec
        assert sqlite_vec is not None
        serialize = sqlite_vec.serialize_float32
        rows = self.database.connection.execute(
            f"SELECT rowid, distance FROM {table} WHERE embedding MATCH ? AND k = ? ORDER BY distance",
            (serialize(vector), max(1, limit)),
        ).fetchall()
        placeholders = ",".join("?" for _ in rows)
        by_row = (
            {
                row["row_id"]: row["chunk_id"]
                for row in self.database.connection.execute(
                    f"SELECT row_id, chunk_id FROM vector_entries "
                    f"WHERE collection_key=? AND row_id IN ({placeholders})",
                    (key, *(row["rowid"] for row in rows)),
                ).fetchall()
            }
            if rows
            else {}
        )
        return [
            VectorMatch(chunk_id=by_row[row["rowid"]], distance=float(row["distance"]))
            for row in rows
            if row["rowid"] in by_row
        ]

    def delete_other_models(self, chunk_id: str, provider: str, model: str) -> None:
        self._require()
        rows = self.database.connection.execute(
            "SELECT * FROM vector_entries WHERE chunk_id=? AND provider=? AND model<>?", (chunk_id, provider, model)
        ).fetchall()
        with self.database.transaction():
            for row in rows:
                table = self._table(f"vec_{row['collection_key']}")
                self.database.connection.execute(f"DELETE FROM {table} WHERE rowid=?", (row["row_id"],))
            self.database.connection.execute(
                "DELETE FROM vector_entries WHERE chunk_id=? AND provider=? AND model<>?", (chunk_id, provider, model)
            )
            self.database.connection.execute(
                "DELETE FROM embeddings WHERE chunk_id=? AND provider=? AND model<>?", (chunk_id, provider, model)
            )

    def prune(self, valid_chunk_ids: set[str]) -> None:
        self._require()
        rows = self.database.connection.execute("SELECT * FROM vector_entries").fetchall()
        stale = [row for row in rows if row["chunk_id"] not in valid_chunk_ids]
        with self.database.transaction():
            for row in stale:
                table = self._table(f"vec_{row['collection_key']}")
                self.database.connection.execute(f"DELETE FROM {table} WHERE rowid=?", (row["row_id"],))
                self.database.connection.execute("DELETE FROM vector_entries WHERE row_id=?", (row["row_id"],))
