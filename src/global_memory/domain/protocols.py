"""Ports owned by the domain/application side of the architecture."""

from __future__ import annotations

from typing import Any, Protocol

from global_memory.domain.models import MemoryDraft, MemoryStatus, StoredMemory


class MemoryRepository(Protocol):
    """Durable memory operations required by application services."""

    def get(self, memory_id: str) -> StoredMemory: ...

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
    ) -> StoredMemory: ...
