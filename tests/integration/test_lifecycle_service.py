from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from global_memory.application.memory_service import MemoryService
from global_memory.domain.models import MemoryDraft, MemoryStatus
from global_memory.errors import ErrorCode, GlobalMemoryError
from global_memory.index.database import IndexDatabase
from global_memory.index.mutations import SQLiteMutationStore
from global_memory.vault.repository import VaultRepository

pytestmark = pytest.mark.integration
NOW = datetime(2026, 7, 11, 11, 0, tzinfo=UTC)


def draft(title: str = "Safe retries", content: str = "# Summary\n\nUse request IDs.\n") -> MemoryDraft:
    return MemoryDraft(
        title=title,
        content=content,
        type="decision",
        scope="project",
        project="Global Memory",
        tags=["idempotency"],
    )


def service(tmp_path: Path, at: datetime = NOW, changes: list[list[str]] | None = None) -> MemoryService:
    repository = VaultRepository(tmp_path / "vault", tmp_path / "data" / "audit.jsonl", clock=lambda: at)
    mutations = SQLiteMutationStore(IndexDatabase(tmp_path / "data" / "memory.db"))
    return MemoryService(
        repository, mutation_store=mutations, on_change=changes.append if changes is not None else None
    )


def test_duplicate_detection_refuses_exact_and_close_matches_unless_forced(tmp_path: Path) -> None:
    memories = service(tmp_path)
    first = memories.remember(draft(), request_id="remember-1")

    with pytest.raises(GlobalMemoryError) as exact:
        memories.remember(draft(), request_id="remember-2")
    assert exact.value.code is ErrorCode.POSSIBLE_DUPLICATE
    assert exact.value.details["duplicates"][0]["id"] == first.metadata.id
    assert exact.value.details["duplicates"][0]["match"] == "exact_content"

    close = draft(title="Safe retry", content="# Summary\n\nUse stable request IDs.\n")
    with pytest.raises(GlobalMemoryError) as similar:
        memories.remember(close, request_id="remember-3")
    assert similar.value.code is ErrorCode.POSSIBLE_DUPLICATE

    forced = memories.remember(close, request_id="remember-4", force=True)
    assert forced.metadata.id != first.metadata.id


def test_idempotent_retry_returns_original_and_payload_reuse_conflicts(tmp_path: Path) -> None:
    memories = service(tmp_path)
    first = memories.remember(draft(), request_id="stable-request")
    retried = memories.remember(draft(), request_id="stable-request")
    assert retried.metadata.id == first.metadata.id
    assert retried.version == first.version
    assert len(memories.list_memories()) == 1

    with pytest.raises(GlobalMemoryError) as caught:
        memories.remember(draft(title="Different"), request_id="stable-request", force=True)
    assert caught.value.code is ErrorCode.REQUEST_ID_CONFLICT


def test_update_section_patch_preserves_other_sections_and_notifies_once(tmp_path: Path) -> None:
    changes: list[list[str]] = []
    first_service = service(tmp_path, changes=changes)
    created = first_service.remember(
        draft(content="# Note\n\n## Summary\n\nOld summary.\n\n## Evidence\n\nKeep this.\n"),
        request_id="create",
    )
    updated = service(tmp_path, NOW + timedelta(minutes=1), changes).update(
        created.metadata.id,
        created.version,
        request_id="update",
        metadata_patch={"future_property": "preserved"},
        section_patch={"Summary": "New summary."},
    )
    assert "## Summary\n\nNew summary." in updated.body
    assert "## Evidence\n\nKeep this." in updated.body
    assert updated.metadata.model_extra and updated.metadata.model_extra["future_property"] == "preserved"
    assert len(changes) == 2

    service(tmp_path, NOW + timedelta(minutes=2), changes).update(
        created.metadata.id,
        created.version,
        request_id="update",
        metadata_patch={"future_property": "preserved"},
        section_patch={"Summary": "New summary."},
    )
    assert len(changes) == 2


def test_supersede_is_reciprocal_and_replay_safe(tmp_path: Path) -> None:
    initial = service(tmp_path)
    old_candidate = initial.remember(draft(title="Old rule"), request_id="old")
    old = service(tmp_path, NOW + timedelta(minutes=1)).approve(
        old_candidate.metadata.id, old_candidate.version, request_id="approve-old"
    )
    replacement = service(tmp_path, NOW + timedelta(minutes=2)).remember(
        draft(title="New rule", content="# Summary\n\nUse durable request IDs.\n"),
        request_id="new",
    )

    result = service(tmp_path, NOW + timedelta(minutes=3)).supersede(
        old.metadata.id,
        replacement_id=replacement.metadata.id,
        reason="Improved guidance",
        request_id="supersede",
    )
    assert result.old.metadata.status is MemoryStatus.SUPERSEDED
    assert result.old.metadata.superseded_by == result.replacement.metadata.id
    assert result.replacement.metadata.status is MemoryStatus.ACTIVE
    assert result.replacement.metadata.supersedes == [result.old.metadata.id]

    replay = service(tmp_path, NOW + timedelta(minutes=4)).supersede(
        old.metadata.id,
        replacement_id=replacement.metadata.id,
        reason="Improved guidance",
        request_id="supersede",
    )
    assert replay.old.version == result.old.version
    assert replay.replacement.version == result.replacement.version


def test_archive_default_and_explicit_hard_delete_tombstone(tmp_path: Path) -> None:
    created = service(tmp_path).remember(draft(), request_id="create")
    active = service(tmp_path, NOW + timedelta(minutes=1)).approve(
        created.metadata.id, created.version, request_id="approve"
    )
    archived = service(tmp_path, NOW + timedelta(minutes=2)).forget(
        active.metadata.id, reason="Stale", request_id="forget"
    )
    assert archived.metadata.status is MemoryStatus.ARCHIVED
    assert archived.path.exists()

    deleted = service(tmp_path, NOW + timedelta(minutes=3)).archive(
        archived.metadata.id,
        reason="User explicitly requested deletion",
        request_id="delete",
        hard_delete=True,
    )
    assert deleted.hard_deleted
    assert not archived.path.exists()
    tombstones = (tmp_path / "data" / "tombstones.jsonl").read_text()
    assert archived.metadata.id in tombstones
    assert "Use request IDs" not in tombstones
