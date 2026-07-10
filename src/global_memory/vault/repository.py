"""Atomic Markdown repository with optimistic concurrency and audit events."""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from global_memory.domain.lifecycle import transition
from global_memory.domain.models import MemoryDraft, MemoryMetadata, MemoryStatus, StoredMemory, metadata_with_patch
from global_memory.errors import ErrorCode, GlobalMemoryError
from global_memory.vault.markdown import parse_note, render_note
from global_memory.vault.paths import canonical_path, safe_vault_path


class VaultRepository:
    """Read and mutate managed Markdown without generated-index dependencies."""

    def __init__(self, vault_path: Path, audit_path: Path, *, clock: Callable[[], datetime] | None = None) -> None:
        self.vault_path = vault_path
        self.audit_path = audit_path
        self._clock = clock or (lambda: datetime.now(UTC))
        self.vault_path.mkdir(parents=True, exist_ok=True)
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)

    def _managed_files(self) -> list[Path]:
        return sorted(
            path
            for path in self.vault_path.rglob("*.md")
            if not any(part.startswith(".") for part in path.relative_to(self.vault_path).parts)
        )

    def get(self, memory_id: str) -> StoredMemory:
        matches: list[StoredMemory] = []
        for path in self._managed_files():
            try:
                parsed = parse_note(path.read_text())
            except GlobalMemoryError:
                continue
            if parsed.metadata.id == memory_id:
                matches.append(StoredMemory(parsed.metadata, parsed.body, path, self.vault_path))
        if not matches:
            raise GlobalMemoryError(
                ErrorCode.NOTE_NOT_FOUND,
                "No memory has the requested ID.",
                details={"id": memory_id},
                remediation="Search for the memory again and use its immutable ID.",
            )
        if len(matches) > 1:
            raise GlobalMemoryError(
                ErrorCode.DUPLICATE_ID,
                "Multiple Vault notes have the same immutable memory ID.",
                details={"id": memory_id, "paths": [str(match.relative_path) for match in matches]},
                remediation="Resolve the duplicate notes explicitly; neither copy was selected.",
            )
        return matches[0]

    def create_candidate(self, draft: MemoryDraft, *, memory_id: str | None = None) -> StoredMemory:
        now = self._clock()
        metadata = MemoryMetadata(
            id=memory_id or f"mem_{uuid.uuid4()}",
            title=draft.title,
            type=draft.type,
            scope=draft.scope,
            project=draft.project,
            status=MemoryStatus.CANDIDATE,
            confidence=draft.confidence,
            importance=draft.importance,
            created_at=now,
            updated_at=now,
            tags=draft.tags,
            links=draft.links,
            source_kind=draft.source_kind,
            source_ref=draft.source_ref,
            supersedes=[],
            superseded_by=None,
        )
        path = safe_vault_path(self.vault_path, canonical_path(metadata))
        if path.exists():
            raise GlobalMemoryError(
                ErrorCode.DUPLICATE_ID,
                "The candidate destination already exists.",
                details={"path": str(path.relative_to(self.vault_path)), "id": metadata.id},
            )
        self._atomic_write(path, render_note(metadata, draft.content))
        self._audit("candidate_created", metadata.id, path, now)
        return StoredMemory(metadata, draft.content, path, self.vault_path)

    def update(
        self,
        memory_id: str,
        *,
        expected_updated_at: str,
        metadata_patch: dict[str, Any] | None = None,
        body: str | None = None,
    ) -> StoredMemory:
        current = self.get(memory_id)
        if current.version != expected_updated_at:
            raise GlobalMemoryError(
                ErrorCode.VERSION_CONFLICT,
                "The memory changed after it was read.",
                details={"id": memory_id, "expected": expected_updated_at, "actual": current.version},
                remediation="Read the memory again and apply the update to the latest version.",
            )
        patch = metadata_patch or {}
        protected = {"id", "created_at", "updated_at", "status", "supersedes", "superseded_by"} & patch.keys()
        if protected:
            raise GlobalMemoryError(
                ErrorCode.NOTE_INVALID,
                "The update attempted to change immutable or lifecycle-managed fields.",
                details={"fields": sorted(protected)},
                remediation="Use the explicit lifecycle operation for status or supersession changes.",
            )
        now = self._clock()
        if now <= current.metadata.updated_at:
            now = current.metadata.updated_at + timedelta(microseconds=1)
        updated_metadata = metadata_with_patch(current.metadata, patch, updated_at=now)
        updated_body = current.body if body is None else body
        self._atomic_write(current.path, render_note(updated_metadata, updated_body))
        self._audit("memory_updated", memory_id, current.path, now, fields=sorted(patch))
        return StoredMemory(updated_metadata, updated_body, current.path, self.vault_path)

    def change_status(
        self,
        memory_id: str,
        target: MemoryStatus,
        *,
        expected_updated_at: str | None = None,
        reason: str | None = None,
        superseded_by: str | None = None,
    ) -> StoredMemory:
        """Validate, persist, and canonically route one explicit lifecycle transition."""
        current = self.get(memory_id)
        if expected_updated_at is not None and current.version != expected_updated_at:
            raise GlobalMemoryError(
                ErrorCode.VERSION_CONFLICT,
                "The memory changed after it was read.",
                details={"id": memory_id, "expected": expected_updated_at, "actual": current.version},
                remediation="Read the memory again and apply the lifecycle action to the latest version.",
            )
        now = self._clock()
        if now <= current.metadata.updated_at:
            now = current.metadata.updated_at + timedelta(microseconds=1)
        updated_metadata = transition(current.metadata, target, at=now, superseded_by=superseded_by)
        if reason is not None:
            values = updated_metadata.model_dump()
            values["lifecycle_reason"] = reason
            updated_metadata = MemoryMetadata.model_validate(values)
        destination = safe_vault_path(self.vault_path, canonical_path(updated_metadata))
        rendered = render_note(updated_metadata, current.body)
        if destination == current.path:
            self._atomic_write(destination, rendered)
        else:
            if destination.exists():
                raise GlobalMemoryError(
                    ErrorCode.DUPLICATE_ID,
                    "The lifecycle destination already exists.",
                    details={"id": memory_id, "path": str(destination.relative_to(self.vault_path))},
                )
            self._atomic_write(destination, rendered)
            try:
                current.path.unlink()
            except OSError:
                destination.unlink(missing_ok=True)
                raise
        self._audit(
            f"memory_{target.value}",
            memory_id,
            destination,
            now,
            reason_present=reason is not None,
        )
        return StoredMemory(updated_metadata, current.body, destination, self.vault_path)

    def _atomic_write(self, destination: Path, text: str) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
        try:
            with temporary.open("x", encoding="utf-8", newline="") as stream:
                stream.write(text)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)

    def _audit(
        self,
        event: str,
        memory_id: str,
        path: Path,
        at: datetime,
        **safe_details: Any,
    ) -> None:
        record = {
            "event_id": str(uuid.uuid4()),
            "event": event,
            "memory_id": memory_id,
            "relative_path": str(path.relative_to(self.vault_path)),
            "at": at.isoformat(),
            "details": safe_details,
        }
        with self.audit_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
