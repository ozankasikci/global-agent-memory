"""Ports owned by the domain/application side of the architecture."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from global_memory.domain.models import HardDeleteResult, MemoryDraft, MemoryStatus, StoredMemory, SupersedeResult


@dataclass(frozen=True, slots=True)
class MutationRecord:
    operation: str
    payload_hash: str
    result: dict[str, Any]


class MutationStore(Protocol):
    """Idempotent mutation receipts in disposable generated state."""

    def get(self, request_id: str) -> MutationRecord | None: ...

    def save(self, request_id: str, record: MutationRecord) -> None: ...


class MemoryRepository(Protocol):
    """Durable memory operations required by application services."""

    def get(self, memory_id: str) -> StoredMemory: ...

    def list_memories(self) -> list[StoredMemory]: ...

    def create_candidate(self, draft: MemoryDraft, *, memory_id: str | None = None) -> StoredMemory: ...

    def update(
        self,
        memory_id: str,
        *,
        expected_updated_at: str,
        metadata_patch: dict[str, Any] | None = None,
        body: str | None = None,
    ) -> StoredMemory: ...

    def change_status(
        self,
        memory_id: str,
        target: MemoryStatus,
        *,
        expected_updated_at: str | None = None,
        reason: str | None = None,
        superseded_by: str | None = None,
        destination_override: str | None = None,
    ) -> StoredMemory: ...

    def supersede(self, old_id: str, replacement_id: str, *, reason: str) -> SupersedeResult: ...

    def hard_delete(self, memory_id: str, *, reason: str) -> HardDeleteResult: ...
