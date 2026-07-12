from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from global_memory.dashboard import serialize_memory
from global_memory.domain.models import MemoryDraft, MemoryScope, StoredMemory, metadata_with_patch
from global_memory.errors import ErrorCode, GlobalMemoryError
from global_memory.mcp.server import _dispatch, build_container
from global_memory.retrieval.search import SearchRequest
from global_memory.vault.markdown import render_note

pytestmark = pytest.mark.integration


def _active_memory(container, *, title: str, content: str) -> StoredMemory:
    candidate = container.memory.remember(
        MemoryDraft(
            title=title,
            content=content,
            type="reference",
            scope=MemoryScope.GLOBAL,
        ),
        request_id=f"remember-{title}",
        force=True,
    )
    return container.memory.approve(candidate.metadata.id, candidate.version, request_id=f"approve-{title}")


def _protected(container, memory: StoredMemory, **policy: object) -> StoredMemory:
    return container.memory.update(
        memory.metadata.id,
        memory.version,
        request_id=f"protect-{memory.metadata.id}-{memory.version}",
        metadata_patch={"visibility": "protected", **policy},
    )


def _request(container, *, permission: str = "manage", duration: str = "session", project: str | None = None):
    return container.access.request(
        agent="Claude Code",
        purpose="Investigate deployment failure",
        query="production topology",
        project=project,
        permission=permission,
        duration=duration,
    )


def test_owner_can_downgrade_and_select_exact_protected_scope(tmp_path: Path) -> None:
    container = build_container(tmp_path / "vault", tmp_path / "state")
    first = _protected(
        container,
        _active_memory(
            container,
            title="Production topology primary",
            content="# Reference\n\nProduction topology uses the primary edge service.",
        ),
        max_permission="edit",
    )
    second = _protected(
        container,
        _active_memory(
            container,
            title="Production topology secondary",
            content="# Reference\n\nProduction topology includes a secondary failover service.",
        ),
        max_permission="manage",
    )

    requested = _request(container)
    state = container.access.dashboard_state()
    pending = next(item for item in state["requests"] if item["id"] == requested["request_id"])
    assert {match["title"] for match in pending["matches"]} == {
        "Production topology primary",
        "Production topology secondary",
    }
    assert {match["max_permission"] for match in pending["matches"]} == {"edit", "manage"}

    approved = container.access.approve(
        requested["request_id"],
        duration="15m",
        permission="edit",
        memory_ids=[first.metadata.id],
    )
    grant = approved["grant"]["id"]
    granted_page = container.search.search(
        SearchRequest(query="production topology", mode="keyword", access_grant=grant)
    )
    assert [result.memory_id for result in granted_page.results] == [first.metadata.id]
    with pytest.raises(GlobalMemoryError) as unselected:
        _dispatch(container, "memory_get", {"id": second.metadata.id, "access_grant": grant})
    assert unselected.value.code is ErrorCode.ACCESS_GRANT_INVALID


def test_approval_rejects_permission_elevation_and_duration_extension(tmp_path: Path) -> None:
    container = build_container(tmp_path / "vault", tmp_path / "state")
    memory = _protected(
        container,
        _active_memory(
            container,
            title="Production topology",
            content="# Reference\n\nProduction topology uses an edge service.",
        ),
        max_permission="manage",
    )
    requested = _request(container, permission="read", duration="15m")

    with pytest.raises(GlobalMemoryError) as elevation:
        container.access.approve(
            requested["request_id"],
            duration="15m",
            permission="edit",
            memory_ids=[memory.metadata.id],
        )
    assert elevation.value.code is ErrorCode.UNAUTHORIZED
    assert container.access.status(requested["request_id"])["status"] == "pending"

    with pytest.raises(GlobalMemoryError) as extension:
        container.access.approve(
            requested["request_id"],
            duration="session",
            permission="read",
            memory_ids=[memory.metadata.id],
        )
    assert extension.value.code is ErrorCode.UNAUTHORIZED


def test_approval_rejects_out_of_scope_stale_and_project_restricted_memories(tmp_path: Path) -> None:
    container = build_container(tmp_path / "vault", tmp_path / "state")
    matched = _protected(
        container,
        _active_memory(
            container,
            title="Production topology matched",
            content="# Reference\n\nProduction topology matched context.",
        ),
        allowed_projects=["Alpha"],
        max_permission="manage",
    )
    outside = _protected(
        container,
        _active_memory(
            container,
            title="Unrelated private note",
            content="# Reference\n\nUnrelated private material.",
        ),
        max_permission="manage",
    )
    requested = _request(container, project="Alpha")

    with pytest.raises(GlobalMemoryError) as out_of_scope:
        container.access.approve(
            requested["request_id"],
            duration="once",
            permission="read",
            memory_ids=[outside.metadata.id],
        )
    assert out_of_scope.value.code is ErrorCode.ACCESS_GRANT_INVALID

    restricted = container.memory.update(
        matched.metadata.id,
        matched.version,
        request_id="restrict-after-request",
        metadata_patch={"allowed_projects": ["Beta"]},
    )
    assert restricted.metadata.allowed_projects == ["Beta"]
    with pytest.raises(GlobalMemoryError) as project_restricted:
        container.access.approve(
            requested["request_id"],
            duration="once",
            permission="read",
            memory_ids=[matched.metadata.id],
        )
    assert project_restricted.value.code is ErrorCode.ACCESS_GRANT_INVALID

    requested_stale = _request(container)
    stale = container.memory.update(
        matched.metadata.id,
        restricted.version,
        request_id="seal-after-request",
        metadata_patch={"visibility": "sealed", "allowed_projects": []},
    )
    assert stale.metadata.visibility.value == "sealed"
    with pytest.raises(GlobalMemoryError) as no_longer_protected:
        container.access.approve(
            requested_stale["request_id"],
            duration="once",
            permission="read",
            memory_ids=[matched.metadata.id],
        )
    assert no_longer_protected.value.code in {ErrorCode.ACCESS_GRANT_INVALID, ErrorCode.VERSION_CONFLICT}


def test_per_access_policy_forces_one_retrieval(tmp_path: Path) -> None:
    container = build_container(tmp_path / "vault", tmp_path / "state")
    memory = _protected(
        container,
        _active_memory(
            container,
            title="Production topology per access",
            content="# Reference\n\nProduction topology requires per-access review.",
        ),
        access_policy="per_access",
        max_permission="read",
    )
    requested = _request(container, permission="read", duration="session")

    with pytest.raises(GlobalMemoryError) as timed:
        container.access.approve(
            requested["request_id"],
            duration="15m",
            permission="read",
            memory_ids=[memory.metadata.id],
        )
    assert timed.value.code is ErrorCode.UNAUTHORIZED

    approved = container.access.approve(
        requested["request_id"],
        duration="once",
        permission="read",
        memory_ids=[memory.metadata.id],
    )
    assert approved["grant"]["remaining_uses"] == 1


def test_policy_change_revokes_active_grant_without_auditing_content(tmp_path: Path) -> None:
    container = build_container(tmp_path / "vault", tmp_path / "state")
    memory = _protected(
        container,
        _active_memory(
            container,
            title="Production topology confidential title",
            content="# Reference\n\nProduction topology confidential body marker.",
        ),
        max_permission="edit",
    )
    requested = _request(container, permission="edit", duration="task")
    approved = container.access.approve(
        requested["request_id"],
        duration="task",
        permission="edit",
        memory_ids=[memory.metadata.id],
    )
    grant = approved["grant"]["id"]

    tightened = metadata_with_patch(
        memory.metadata,
        {"max_permission": "read"},
        updated_at=max(datetime.now(UTC), memory.metadata.updated_at + timedelta(microseconds=1)),
    )
    memory.path.write_text(render_note(tightened, memory.body))
    assert container.index_jobs.enqueue(memory.relative_path)
    assert container.index_jobs.process_due().completed == 1
    state = container.access.dashboard_state()
    assert next(item for item in state["grants"] if item["id"] == grant)["status"] == "revoked"
    event = next(item for item in state["events"] if item["grant_id"] == grant and item["action"] == "policy_revoked")
    encoded = str(event)
    assert "confidential title" not in encoded
    assert "confidential body marker" not in encoded
    with pytest.raises(GlobalMemoryError) as revoked:
        _dispatch(container, "memory_get", {"id": memory.metadata.id, "access_grant": grant})
    assert revoked.value.code is ErrorCode.ACCESS_GRANT_INVALID


def test_sealed_memory_is_not_indexed_or_exposed_and_dashboard_redacts_it(tmp_path: Path) -> None:
    container = build_container(tmp_path / "vault", tmp_path / "state")
    active = _active_memory(
        container,
        title="On-call escalation runbook",
        content="# Runbook\n\nEscalate using the private owner-managed path.",
    )
    sealed = container.memory.update(
        active.metadata.id,
        active.version,
        request_id="classify-sealed",
        metadata_patch={"visibility": "sealed", "access_policy": "per_access"},
    )

    chunks = container.database.connection.execute(
        "SELECT COUNT(*) FROM chunks WHERE document_id=?", (sealed.metadata.id,)
    ).fetchone()[0]
    assert chunks == 0
    assert container.search.search(SearchRequest(query="escalation runbook", mode="keyword")).results == ()
    with pytest.raises(GlobalMemoryError) as denied:
        _dispatch(container, "memory_get", {"id": sealed.metadata.id})
    assert denied.value.code is ErrorCode.ACCESS_APPROVAL_REQUIRED

    redacted = serialize_memory(sealed, [sealed])
    assert redacted["title"] == "Sealed memory"
    assert redacted["body"] == ""
    assert redacted["path"] == ""
    revealed = serialize_memory(sealed, [sealed], unlock_sealed=True)
    assert revealed["title"] == "On-call escalation runbook"
    assert "private owner-managed path" in revealed["body"]
