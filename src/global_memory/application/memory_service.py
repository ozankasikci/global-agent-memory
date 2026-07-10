"""Transport-independent memory use cases backed by a repository port."""

from __future__ import annotations

from typing import Any

from global_memory.domain.models import MemoryDraft, MemoryStatus, StoredMemory
from global_memory.domain.protocols import MemoryRepository


class MemoryService:
    """Coordinate explicit lifecycle operations without MCP or index dependencies."""

    def __init__(self, repository: MemoryRepository) -> None:
        self._repository = repository

    def remember(self, draft: MemoryDraft) -> StoredMemory:
        return self._repository.create_candidate(draft)

    def get(self, memory_id: str) -> StoredMemory:
        return self._repository.get(memory_id)

    def update(
        self,
        memory_id: str,
        expected_updated_at: str,
        *,
        metadata_patch: dict[str, Any] | None = None,
        body: str | None = None,
    ) -> StoredMemory:
        return self._repository.update(
            memory_id,
            expected_updated_at=expected_updated_at,
            metadata_patch=metadata_patch,
            body=body,
        )

    def approve(self, memory_id: str, expected_updated_at: str | None = None) -> StoredMemory:
        return self._repository.change_status(
            memory_id,
            MemoryStatus.ACTIVE,
            expected_updated_at=expected_updated_at,
        )

    def reject(self, memory_id: str, expected_updated_at: str | None = None, *, reason: str) -> StoredMemory:
        return self._repository.change_status(
            memory_id,
            MemoryStatus.REJECTED,
            expected_updated_at=expected_updated_at,
            reason=reason,
        )

    def archive(self, memory_id: str, expected_updated_at: str | None = None, *, reason: str) -> StoredMemory:
        return self._repository.change_status(
            memory_id,
            MemoryStatus.ARCHIVED,
            expected_updated_at=expected_updated_at,
            reason=reason,
        )
