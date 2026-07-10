"""SQLite-backed idempotent mutation receipts."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from global_memory.domain.protocols import MutationRecord
from global_memory.index.database import IndexDatabase


class SQLiteMutationStore:
    """Persist mutation payload hashes and original result snapshots."""

    def __init__(self, database: IndexDatabase) -> None:
        self.database = database

    def get(self, request_id: str) -> MutationRecord | None:
        row = self.database.connection.execute(
            "SELECT operation, payload_hash, result_json FROM mutation_requests WHERE request_id = ?", (request_id,)
        ).fetchone()
        if row is None:
            return None
        return MutationRecord(
            operation=row["operation"],
            payload_hash=row["payload_hash"],
            result=json.loads(row["result_json"]),
        )

    def save(self, request_id: str, record: MutationRecord) -> None:
        with self.database.transaction():
            self.database.connection.execute(
                "INSERT INTO mutation_requests(request_id, operation, payload_hash, result_json, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    request_id,
                    record.operation,
                    record.payload_hash,
                    json.dumps(record.result, ensure_ascii=False, sort_keys=True),
                    datetime.now(UTC).isoformat(),
                ),
            )
