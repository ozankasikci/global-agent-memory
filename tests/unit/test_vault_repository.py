from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from global_memory.application.memory_service import MemoryService
from global_memory.domain.lifecycle import transition
from global_memory.domain.models import MemoryDraft, MemoryStatus
from global_memory.errors import ErrorCode, GlobalMemoryError
from global_memory.vault.paths import canonical_path, safe_vault_path
from global_memory.vault.repository import VaultRepository

NOW = datetime(2026, 7, 11, 9, 0, tzinfo=UTC)
LATER = NOW + timedelta(minutes=1)


def draft() -> MemoryDraft:
    return MemoryDraft(
        title="Atomic writes",
        content="# Atomic writes\n\nKeep the original on failure.\n",
        type="decision",
        scope="project",
        project="Global Memory",
        confidence=0.9,
        importance=0.8,
        tags=["safety"],
        links=["[[Global Memory]]"],
        source_kind="manual",
    )


def repository(tmp_path: Path, clock: datetime = NOW) -> VaultRepository:
    return VaultRepository(tmp_path / "vault", tmp_path / "data" / "audit.jsonl", clock=lambda: clock)


def test_candidate_create_get_and_stale_update(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    created = repo.create_candidate(draft(), memory_id="mem_12345678-1234-4234-8234-123456789abc")
    assert created.relative_path.parent.as_posix() == "00 Inbox/AI Candidates"
    assert created.metadata.status is MemoryStatus.CANDIDATE

    updated_repo = repository(tmp_path, LATER)
    updated = updated_repo.update(
        created.metadata.id,
        expected_updated_at=created.version,
        metadata_patch={"importance": 1.0, "future": "kept"},
        body="# Changed\n",
    )
    assert updated.body == "# Changed\n"
    assert updated.metadata.model_extra == {"future": "kept"}

    with pytest.raises(GlobalMemoryError) as caught:
        updated_repo.update(
            created.metadata.id, expected_updated_at=created.version, metadata_patch={"importance": 0.1}
        )
    assert caught.value.code is ErrorCode.VERSION_CONFLICT
    assert updated_repo.get(created.metadata.id).body == "# Changed\n"


def test_ids_and_creation_time_are_immutable(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    created = repo.create_candidate(draft())
    for patch in ({"id": "mem_changed"}, {"created_at": LATER.isoformat()}):
        with pytest.raises(GlobalMemoryError) as caught:
            repo.update(created.metadata.id, expected_updated_at=created.version, metadata_patch=patch)
        assert caught.value.code is ErrorCode.NOTE_INVALID


def test_atomic_write_failure_preserves_original(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = repository(tmp_path)
    created = repo.create_candidate(draft())
    original = created.path.read_bytes()

    def fail_replace(source: Path, destination: Path) -> None:
        raise OSError("simulated rename failure")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated"):
        repo.update(created.metadata.id, expected_updated_at=created.version, body="lost")

    assert created.path.read_bytes() == original
    assert not list(created.path.parent.glob(".*.tmp"))


def test_traversal_and_symlink_escape_are_rejected(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (vault / "escape").symlink_to(outside, target_is_directory=True)

    for path in (Path("../outside/note.md"), Path("escape/note.md"), outside / "note.md"):
        with pytest.raises(GlobalMemoryError) as caught:
            safe_vault_path(vault, path)
        assert caught.value.code is ErrorCode.PATH_OUTSIDE_VAULT


def test_canonical_routing_is_status_scope_and_type_aware(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    created = repo.create_candidate(draft())
    active = created.metadata.model_copy(update={"status": MemoryStatus.ACTIVE})
    assert canonical_path(active).parent.as_posix() == "20 Projects/Global Memory/Decisions"
    assert canonical_path(active.model_copy(update={"status": MemoryStatus.ARCHIVED})).parts[0] == "90 Archive"
    assert canonical_path(active.model_copy(update={"status": MemoryStatus.REJECTED})).parent.as_posix() == (
        "90 Archive/Rejected"
    )


def test_duplicate_ids_are_never_silently_selected(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    created = repo.create_candidate(draft())
    duplicate = repo.vault_path / "10 Global" / "copy.md"
    duplicate.parent.mkdir(parents=True, exist_ok=True)
    duplicate.write_bytes(created.path.read_bytes())

    with pytest.raises(GlobalMemoryError) as caught:
        repo.get(created.metadata.id)
    assert caught.value.code is ErrorCode.DUPLICATE_ID


def test_lifecycle_rules_and_audit_events_do_not_contain_bodies(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    created = repo.create_candidate(draft())
    active = transition(created.metadata, MemoryStatus.ACTIVE, at=LATER)
    assert active.status is MemoryStatus.ACTIVE
    with pytest.raises(GlobalMemoryError):
        transition(active, MemoryStatus.REJECTED, at=LATER + timedelta(minutes=1))

    events = [json.loads(line) for line in repo.audit_path.read_text().splitlines()]
    assert events[0]["memory_id"] == created.metadata.id
    assert "content" not in events[0]
    assert "body" not in events[0]


def test_lifecycle_operations_route_through_application_service(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    service = MemoryService(repo)
    candidate = service.remember(draft())

    active = MemoryService(repository(tmp_path, LATER)).approve(candidate.metadata.id, candidate.version)
    assert active.metadata.status is MemoryStatus.ACTIVE
    assert active.relative_path.parent.as_posix() == "20 Projects/Global Memory/Decisions"
    assert not candidate.path.exists()

    second = MemoryService(repository(tmp_path, LATER)).remember(draft(), force=True)
    rejected = MemoryService(repository(tmp_path, LATER + timedelta(minutes=1))).reject(
        second.metadata.id, second.version, reason="Unverified"
    )
    assert rejected.metadata.status is MemoryStatus.REJECTED
    assert rejected.relative_path.parent.as_posix() == "90 Archive/Rejected"
    assert rejected.metadata.model_extra == {"lifecycle_reason": "Unverified"}

    archived = MemoryService(repository(tmp_path, LATER + timedelta(minutes=2))).archive(
        active.metadata.id, active.version, reason="No longer applicable"
    )
    assert archived.metadata.status is MemoryStatus.ARCHIVED
    assert archived.relative_path.parts[0] == "90 Archive"


def test_supersede_second_write_failure_restores_both_originals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = MemoryService(repository(tmp_path)).remember(draft())
    active = MemoryService(repository(tmp_path, LATER)).approve(first.metadata.id, first.version)
    replacement = MemoryService(repository(tmp_path, LATER)).remember(
        MemoryDraft(
            title="Replacement",
            content="# Replacement\n",
            type="decision",
            scope="project",
            project="Global Memory",
        )
    )
    old_bytes = active.path.read_bytes()
    replacement_bytes = replacement.path.read_bytes()
    real_replace = os.replace
    calls = 0

    def fail_second_replace(source: Path, destination: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated second write failure")
        real_replace(source, destination)

    monkeypatch.setattr(os, "replace", fail_second_replace)
    with pytest.raises(OSError, match="second write"):
        repository(tmp_path, LATER + timedelta(minutes=1)).supersede(
            active.metadata.id, replacement.metadata.id, reason="Replacement"
        )

    assert active.path.read_bytes() == old_bytes
    assert replacement.path.read_bytes() == replacement_bytes
