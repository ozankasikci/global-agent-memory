"""Transport-independent, candidate-first, replay-safe memory use cases."""

from __future__ import annotations

import hashlib
import json
import re
import threading
import unicodedata
from collections.abc import Callable
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from global_memory.domain.models import (
    HardDeleteResult,
    MemoryDraft,
    MemoryMetadata,
    MemoryStatus,
    StoredMemory,
    SupersedeResult,
)
from global_memory.domain.protocols import MemoryRepository, MutationRecord, MutationStore
from global_memory.errors import ErrorCode, GlobalMemoryError

type MutationResult = StoredMemory | SupersedeResult | HardDeleteResult
type ChangeCallback = Callable[[list[str]], None]


def _normalized(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _patch_sections(body: str, patches: dict[str, str]) -> str:
    updated = body
    for requested_heading, replacement in patches.items():
        lines = updated.splitlines(keepends=True)
        match_index: int | None = None
        match_level = 0
        for index, line in enumerate(lines):
            match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line.rstrip("\r\n"))
            if match and match.group(2).strip().casefold() == requested_heading.strip().casefold():
                match_index = index
                match_level = len(match.group(1))
                break
        rendered = replacement.strip() + "\n"
        if match_index is None:
            separator = "" if not updated or updated.endswith("\n\n") else "\n"
            updated = f"{updated}{separator}## {requested_heading}\n\n{rendered}"
            continue
        end = len(lines)
        for index in range(match_index + 1, len(lines)):
            following = re.match(r"^(#{1,6})\s+", lines[index])
            if following and len(following.group(1)) <= match_level:
                end = index
                break
        prefix = lines[: match_index + 1]
        if not prefix[-1].endswith("\n"):
            prefix[-1] += "\n"
        lines = [*prefix, "\n", rendered, "\n", *lines[end:]]
        updated = "".join(lines)
    return updated


def _stored_to_dict(memory: StoredMemory) -> dict[str, Any]:
    return {
        "kind": "stored",
        "metadata": memory.metadata.model_dump(mode="json"),
        "body": memory.body,
        "path": str(memory.path),
        "vault_path": str(memory.vault_path),
    }


def _stored_from_dict(value: dict[str, Any]) -> StoredMemory:
    return StoredMemory(
        metadata=MemoryMetadata.model_validate(value["metadata"]),
        body=str(value["body"]),
        path=Path(value["path"]),
        vault_path=Path(value["vault_path"]),
    )


def _result_to_dict(result: MutationResult) -> dict[str, Any]:
    if isinstance(result, StoredMemory):
        return _stored_to_dict(result)
    if isinstance(result, SupersedeResult):
        return {
            "kind": "supersede",
            "old": _stored_to_dict(result.old),
            "replacement": _stored_to_dict(result.replacement),
        }
    return {
        "kind": "hard_delete",
        "memory_id": result.memory_id,
        "relative_path": str(result.relative_path),
        "hard_deleted": result.hard_deleted,
    }


def _result_from_dict(value: dict[str, Any]) -> MutationResult:
    if value["kind"] == "stored":
        return _stored_from_dict(value)
    if value["kind"] == "supersede":
        return SupersedeResult(old=_stored_from_dict(value["old"]), replacement=_stored_from_dict(value["replacement"]))
    return HardDeleteResult(
        memory_id=str(value["memory_id"]),
        relative_path=Path(value["relative_path"]),
        hard_deleted=bool(value["hard_deleted"]),
    )


class MemoryService:
    """Coordinate explicit lifecycle operations without transport dependencies."""

    def __init__(
        self,
        repository: MemoryRepository,
        *,
        mutation_store: MutationStore | None = None,
        on_change: ChangeCallback | None = None,
    ) -> None:
        self._repository = repository
        self._mutation_store = mutation_store
        self._on_change = on_change
        self._mutation_lock = threading.RLock()

    def _notify(self, memories: list[StoredMemory]) -> None:
        if self._on_change is not None:
            self._on_change([memory.relative_path.as_posix() for memory in memories])

    def _execute(
        self,
        operation: str,
        request_id: str | None,
        payload: dict[str, Any],
        action: Callable[[], MutationResult],
    ) -> MutationResult:
        if request_id is None or self._mutation_store is None:
            return action()
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        payload_hash = hashlib.sha256(encoded.encode()).hexdigest()
        with self._mutation_lock:
            existing = self._mutation_store.get(request_id)
            if existing is not None:
                if existing.operation != operation or existing.payload_hash != payload_hash:
                    raise GlobalMemoryError(
                        ErrorCode.REQUEST_ID_CONFLICT,
                        "The request ID was already used with a different mutation payload.",
                        details={"request_id": request_id, "original_operation": existing.operation},
                        remediation="Generate a new request ID for a different mutation.",
                    )
                return _result_from_dict(existing.result)
            result = action()
            self._mutation_store.save(
                request_id,
                MutationRecord(operation=operation, payload_hash=payload_hash, result=_result_to_dict(result)),
            )
            return result

    def _duplicates(self, draft: MemoryDraft) -> list[dict[str, Any]]:
        normalized_content = _normalized(draft.content)
        duplicates: list[dict[str, Any]] = []
        for memory in self._repository.list_memories():
            metadata = memory.metadata
            if metadata.status not in {MemoryStatus.CANDIDATE, MemoryStatus.ACTIVE}:
                continue
            if metadata.scope != draft.scope or metadata.project != draft.project:
                continue
            match = ""
            if _normalized(memory.body) == normalized_content:
                match = "exact_content"
            else:
                title_score = SequenceMatcher(None, _normalized(metadata.title), _normalized(draft.title)).ratio()
                body_score = SequenceMatcher(None, _normalized(memory.body), normalized_content).ratio()
                if title_score >= 0.8 and body_score >= 0.72:
                    match = "close_title_body"
            if match:
                duplicates.append(
                    {
                        "id": metadata.id,
                        "title": metadata.title,
                        "match": match,
                        "excerpt": memory.body[:200],
                    }
                )
        return duplicates

    def remember(self, draft: MemoryDraft, *, request_id: str | None = None, force: bool = False) -> StoredMemory:
        payload = {"draft": draft.model_dump(mode="json"), "force": force}

        def action() -> MutationResult:
            duplicates = self._duplicates(draft)
            if duplicates and not force:
                raise GlobalMemoryError(
                    ErrorCode.POSSIBLE_DUPLICATE,
                    "The candidate is likely to duplicate an existing memory.",
                    details={"duplicates": duplicates},
                    remediation=(
                        "Review the possible duplicates, then retry with force=true only if "
                        "a separate note is intended."
                    ),
                )
            created = self._repository.create_candidate(draft)
            self._notify([created])
            return created

        result = self._execute("remember", request_id, payload, action)
        if not isinstance(result, StoredMemory):
            raise RuntimeError("invalid idempotent result for remember")
        return result

    def get(self, memory_id: str) -> StoredMemory:
        return self._repository.get(memory_id)

    def list_memories(self) -> list[StoredMemory]:
        return self._repository.list_memories()

    def update(
        self,
        memory_id: str,
        expected_updated_at: str,
        *,
        request_id: str | None = None,
        metadata_patch: dict[str, Any] | None = None,
        body: str | None = None,
        section_patch: dict[str, str] | None = None,
    ) -> StoredMemory:
        if body is not None and section_patch:
            raise GlobalMemoryError(
                ErrorCode.NOTE_INVALID,
                "A full body replacement and section patch cannot be applied together.",
                remediation="Choose either body or section_patch for one update.",
            )
        payload = {
            "id": memory_id,
            "expected_updated_at": expected_updated_at,
            "metadata_patch": metadata_patch,
            "body": body,
            "section_patch": section_patch,
        }

        def action() -> MutationResult:
            updated_body = body
            if section_patch:
                updated_body = _patch_sections(self._repository.get(memory_id).body, section_patch)
            updated = self._repository.update(
                memory_id,
                expected_updated_at=expected_updated_at,
                metadata_patch=metadata_patch,
                body=updated_body,
            )
            self._notify([updated])
            return updated

        result = self._execute("update", request_id, payload, action)
        if not isinstance(result, StoredMemory):
            raise RuntimeError("invalid idempotent result for update")
        return result

    def approve(
        self,
        memory_id: str,
        expected_updated_at: str | None = None,
        *,
        request_id: str | None = None,
    ) -> StoredMemory:
        payload = {"id": memory_id, "expected_updated_at": expected_updated_at}

        def action() -> MutationResult:
            approved = self._repository.change_status(
                memory_id, MemoryStatus.ACTIVE, expected_updated_at=expected_updated_at
            )
            self._notify([approved])
            return approved

        result = self._execute("approve", request_id, payload, action)
        if not isinstance(result, StoredMemory):
            raise RuntimeError("invalid idempotent result for approve")
        return result

    def reject(
        self,
        memory_id: str,
        expected_updated_at: str | None = None,
        *,
        reason: str,
        request_id: str | None = None,
    ) -> StoredMemory:
        payload = {"id": memory_id, "expected_updated_at": expected_updated_at, "reason": reason}

        def action() -> MutationResult:
            rejected = self._repository.change_status(
                memory_id,
                MemoryStatus.REJECTED,
                expected_updated_at=expected_updated_at,
                reason=reason,
            )
            self._notify([rejected])
            return rejected

        result = self._execute("reject", request_id, payload, action)
        if not isinstance(result, StoredMemory):
            raise RuntimeError("invalid idempotent result for reject")
        return result

    def supersede(
        self,
        old_id: str,
        *,
        reason: str,
        request_id: str | None = None,
        replacement_id: str | None = None,
        replacement: MemoryDraft | None = None,
    ) -> SupersedeResult:
        if (replacement_id is None) == (replacement is None):
            raise GlobalMemoryError(
                ErrorCode.NOTE_INVALID,
                "Exactly one replacement_id or replacement must be supplied.",
            )
        payload = {
            "old_id": old_id,
            "reason": reason,
            "replacement_id": replacement_id,
            "replacement": replacement.model_dump(mode="json") if replacement else None,
        }

        def action() -> MutationResult:
            resolved_id = replacement_id
            created: StoredMemory | None = None
            if replacement is not None:
                duplicates = [item for item in self._duplicates(replacement) if item["id"] != old_id]
                if duplicates:
                    raise GlobalMemoryError(
                        ErrorCode.POSSIBLE_DUPLICATE,
                        "The proposed replacement duplicates another applicable memory.",
                        details={"duplicates": duplicates},
                    )
                created = self._repository.create_candidate(replacement)
                resolved_id = created.metadata.id
            assert resolved_id is not None
            try:
                superseded = self._repository.supersede(old_id, resolved_id, reason=reason)
            except BaseException:
                if created is not None:
                    created.path.unlink(missing_ok=True)
                raise
            self._notify([superseded.old, superseded.replacement])
            return superseded

        result = self._execute("supersede", request_id, payload, action)
        if not isinstance(result, SupersedeResult):
            raise RuntimeError("invalid idempotent result for supersede")
        return result

    def archive(
        self,
        memory_id: str,
        expected_updated_at: str | None = None,
        *,
        reason: str,
        request_id: str | None = None,
        hard_delete: bool = False,
    ) -> StoredMemory | HardDeleteResult:
        payload = {
            "id": memory_id,
            "reason": reason,
            "expected_updated_at": expected_updated_at,
            "hard_delete": hard_delete,
        }

        def action() -> MutationResult:
            if hard_delete:
                current = self._repository.get(memory_id)
                deleted = self._repository.hard_delete(memory_id, reason=reason)
                self._notify([current])
                return deleted
            archived = self._repository.change_status(
                memory_id,
                MemoryStatus.ARCHIVED,
                expected_updated_at=expected_updated_at,
                reason=reason,
            )
            self._notify([archived])
            return archived

        result = self._execute("archive", request_id, payload, action)
        if isinstance(result, SupersedeResult):
            raise RuntimeError("invalid idempotent result for archive")
        return result

    def forget(
        self,
        memory_id: str,
        *,
        reason: str,
        request_id: str | None = None,
        expected_updated_at: str | None = None,
    ) -> StoredMemory:
        result = self.archive(
            memory_id,
            reason=reason,
            request_id=request_id,
            expected_updated_at=expected_updated_at,
            hard_delete=False,
        )
        if not isinstance(result, StoredMemory):
            raise RuntimeError("invalid archive result for forget")
        return result
