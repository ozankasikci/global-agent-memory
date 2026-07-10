"""Atomic Markdown repository with optimistic concurrency and audit events."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from global_memory.domain.lifecycle import transition
from global_memory.domain.models import (
    HardDeleteResult,
    MemoryDraft,
    MemoryMetadata,
    MemoryStatus,
    StoredMemory,
    SupersedeResult,
    metadata_with_patch,
)
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

    def list_memories(self) -> list[StoredMemory]:
        """Return every valid managed note, refusing duplicate identities."""
        by_id: dict[str, StoredMemory] = {}
        duplicates: dict[str, list[str]] = {}
        for path in self._managed_files():
            try:
                parsed = parse_note(path.read_text())
            except GlobalMemoryError:
                continue
            stored = StoredMemory(parsed.metadata, parsed.body, path, self.vault_path)
            if parsed.metadata.id in by_id:
                duplicates.setdefault(parsed.metadata.id, [str(by_id[parsed.metadata.id].relative_path)]).append(
                    str(stored.relative_path)
                )
            else:
                by_id[parsed.metadata.id] = stored
        if duplicates:
            raise GlobalMemoryError(
                ErrorCode.DUPLICATE_ID,
                "Duplicate memory IDs prevent an unambiguous Vault listing.",
                details={"duplicates": duplicates},
                remediation="Resolve every duplicate explicitly before mutating memory.",
            )
        return sorted(by_id.values(), key=lambda memory: memory.metadata.id)

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

    def supersede(self, old_id: str, replacement_id: str, *, reason: str) -> SupersedeResult:
        """Write reciprocal lifecycle metadata with rollback on ordinary multi-file failures."""
        old = self.get(old_id)
        replacement = self.get(replacement_id)
        if old.metadata.status is not MemoryStatus.ACTIVE:
            raise GlobalMemoryError(
                ErrorCode.NOTE_INVALID,
                "Only an active memory can be superseded.",
                details={"id": old_id, "status": old.metadata.status.value},
            )
        if replacement.metadata.status not in {MemoryStatus.CANDIDATE, MemoryStatus.ACTIVE}:
            raise GlobalMemoryError(
                ErrorCode.NOTE_INVALID,
                "The replacement must be a candidate or active memory.",
                details={"id": replacement_id, "status": replacement.metadata.status.value},
            )
        now = max(self._clock(), old.metadata.updated_at, replacement.metadata.updated_at) + timedelta(microseconds=1)
        old_values = transition(
            old.metadata, MemoryStatus.SUPERSEDED, at=now, superseded_by=replacement_id
        ).model_dump()
        old_values["lifecycle_reason"] = reason
        new_values = replacement.metadata.model_dump()
        new_values.update(
            status=MemoryStatus.ACTIVE,
            updated_at=now,
            supersedes=list(dict.fromkeys([*replacement.metadata.supersedes, old_id])),
            superseded_by=None,
            lifecycle_reason=reason,
        )
        old_metadata = MemoryMetadata.model_validate(old_values)
        replacement_metadata = MemoryMetadata.model_validate(new_values)
        old_destination = safe_vault_path(self.vault_path, canonical_path(old_metadata))
        replacement_destination = safe_vault_path(self.vault_path, canonical_path(replacement_metadata))
        sources = {old.path: old.path.read_bytes(), replacement.path: replacement.path.read_bytes()}
        destinations = {
            old_destination: render_note(old_metadata, old.body),
            replacement_destination: render_note(replacement_metadata, replacement.body),
        }
        for destination in destinations:
            if destination.exists() and destination not in sources:
                raise GlobalMemoryError(
                    ErrorCode.DUPLICATE_ID,
                    "A supersession destination already exists.",
                    details={"path": str(destination.relative_to(self.vault_path))},
                )
        try:
            for destination, text in destinations.items():
                self._atomic_write(destination, text)
            for source in sources:
                if source not in destinations:
                    source.unlink()
        except BaseException:
            for destination in destinations:
                if destination not in sources:
                    destination.unlink(missing_ok=True)
            for source, content in sources.items():
                self._atomic_write(source, content.decode())
            raise
        self._audit("memory_superseded", old_id, old_destination, now, replacement_id=replacement_id)
        self._audit("memory_replacement_activated", replacement_id, replacement_destination, now, old_id=old_id)
        return SupersedeResult(
            old=StoredMemory(old_metadata, old.body, old_destination, self.vault_path),
            replacement=StoredMemory(replacement_metadata, replacement.body, replacement_destination, self.vault_path),
        )

    def hard_delete(self, memory_id: str, *, reason: str) -> HardDeleteResult:
        """Hard-delete only on explicit invocation and retain a content-free tombstone."""
        current = self.get(memory_id)
        now = self._clock()
        tombstone_path = self.audit_path.parent / "tombstones.jsonl"
        tombstone = {
            "id": memory_id,
            "relative_path": str(current.relative_path),
            "deleted_at": now.isoformat(),
            "reason": reason,
            "content_hash": hashlib.sha256(current.path.read_bytes()).hexdigest(),
        }
        with tombstone_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(tombstone, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        current.path.unlink()
        self._audit("memory_hard_deleted", memory_id, current.path, now, tombstone=True)
        return HardDeleteResult(memory_id=memory_id, relative_path=current.relative_path)

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
