"""Pure lifecycle transition rules."""

from __future__ import annotations

from datetime import datetime

from global_memory.domain.models import MemoryMetadata, MemoryStatus
from global_memory.errors import ErrorCode, GlobalMemoryError

ALLOWED_TRANSITIONS: dict[MemoryStatus, frozenset[MemoryStatus]] = {
    MemoryStatus.CANDIDATE: frozenset({MemoryStatus.ACTIVE, MemoryStatus.REJECTED, MemoryStatus.ARCHIVED}),
    MemoryStatus.ACTIVE: frozenset({MemoryStatus.SUPERSEDED, MemoryStatus.ARCHIVED}),
    MemoryStatus.SUPERSEDED: frozenset({MemoryStatus.ARCHIVED}),
    MemoryStatus.REJECTED: frozenset({MemoryStatus.ARCHIVED}),
    MemoryStatus.ARCHIVED: frozenset(),
}


def transition(
    metadata: MemoryMetadata,
    target: MemoryStatus,
    *,
    at: datetime,
    superseded_by: str | None = None,
) -> MemoryMetadata:
    """Return a validated transitioned entity or a stable lifecycle error."""
    if target not in ALLOWED_TRANSITIONS[metadata.status]:
        raise GlobalMemoryError(
            ErrorCode.NOTE_INVALID,
            f"Cannot transition memory from {metadata.status.value} to {target.value}.",
            details={"id": metadata.id, "from": metadata.status.value, "to": target.value},
            remediation="Read the latest memory state and choose a permitted lifecycle operation.",
        )
    values = metadata.model_dump()
    values.update(status=target, updated_at=at)
    if target is MemoryStatus.SUPERSEDED:
        values["superseded_by"] = superseded_by
    elif target is MemoryStatus.ACTIVE:
        values["superseded_by"] = None
    return MemoryMetadata.model_validate(values)
