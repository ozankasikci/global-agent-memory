from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import anyio
import httpx
import pytest
from starlette.applications import Starlette

import global_memory
from global_memory.dashboard import DashboardSessions, dashboard_routes
from global_memory.dashboard.routes import _dashboard_root
from global_memory.domain.models import MemoryDraft
from global_memory.mcp.server import build_container
from global_memory.projects.models import ProjectDraft


def test_dashboard_root_resolves_packaged_assets() -> None:
    expected = Path(global_memory.__file__).resolve().parent / "_dashboard"

    assert _dashboard_root() == expected
    assert (_dashboard_root() / "index.html").is_file()


def test_dashboard_launch_tickets_are_single_use_and_sessions_expire() -> None:
    now = datetime(2026, 7, 11, tzinfo=UTC)
    opened: list[str] = []
    sessions = DashboardSessions(
        "http://127.0.0.1:8765",
        opener=lambda url: bool(opened.append(url)),
        clock=lambda: now,
    )

    launched = sessions.launch(open_browser=True)
    assert launched["opened"] is False
    assert opened == [launched["url"]]
    ticket = parse_qs(urlsplit(launched["url"]).query)["ticket"][0]
    session = sessions.exchange(ticket)
    assert session is not None and sessions.valid(session)
    assert sessions.exchange(ticket) is None

    now += timedelta(hours=13)
    assert not sessions.valid(session)


@pytest.mark.asyncio
async def test_dashboard_routes_require_session_and_mutate_through_memory_service(tmp_path: Path) -> None:
    container = build_container(tmp_path / "vault", tmp_path / "state")
    container.projects.add(ProjectDraft(name="Alpha"))
    container.projects.add(ProjectDraft(name="Beta"))
    candidate = container.memory.remember(
        MemoryDraft(
            title="Use durable IDs",
            content="# Summary\n\nUse stable request identifiers.\n\n## Evidence\n\nVerified in tests.",
            type="convention",
            scope="project",
            project="Alpha",
            tags=["requests"],
        )
    )
    other_candidate = container.memory.remember(
        MemoryDraft(
            title="Beta-only workflow",
            content="# Summary\n\nThis activity belongs only to Beta.",
            type="convention",
            scope="project",
            project="Beta",
            tags=["beta"],
        )
    )
    shared_candidate = container.memory.remember(
        MemoryDraft(
            title="Organization-wide workflow",
            content="# Summary\n\nThis is shared memory, not Alpha project activity.",
            type="convention",
            scope="organization",
            tags=["shared"],
        )
    )
    rejected_other = container.memory.reject(
        other_candidate.metadata.id,
        other_candidate.version,
        reason="Verification cleanup",
    )
    container.memory.archive(
        rejected_other.metadata.id,
        rejected_other.version,
        reason="Verification cleanup",
        hard_delete=True,
    )
    sessions = DashboardSessions("http://127.0.0.1:8765")
    app = Starlette(routes=dashboard_routes(container, sessions))

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        index = await client.get("/ui/")
        assert index.status_code == 200
        assert "<html" in index.text

        unauthorized = await client.get("/ui/api/bootstrap")
        assert unauthorized.status_code == 401

        launch = sessions.launch(open_browser=False)
        ticket = parse_qs(urlsplit(launch["url"]).query)["ticket"][0]
        exchanged = await client.get(f"/ui/session?ticket={ticket}", follow_redirects=False)
        assert exchanged.status_code == 303

        bootstrap = await client.get("/ui/api/bootstrap?project=Alpha")
        assert bootstrap.status_code == 200
        data = bootstrap.json()["data"]
        assert data["selected_project"] == "Alpha"
        assert data["project_stats"]["Alpha"]["candidates"] == 2
        alpha_candidate = next(item for item in data["candidates"] if item["id"] == candidate.metadata.id)
        assert alpha_candidate["evidence"] == "Verified in tests."
        assert any(item["target"] == "Use durable IDs" for item in data["activity"])
        assert all(item["target"] != other_candidate.metadata.id for item in data["activity"])
        assert all(item["target"] != shared_candidate.metadata.title for item in data["activity"])
        audit_events = [json.loads(line) for line in container.repository.audit_path.read_text().splitlines()]
        deleted_event = next(item for item in audit_events if item["event"] == "memory_hard_deleted")
        assert deleted_event["details"]["project"] == "Beta"

        forbidden = await client.post(
            f"/ui/api/memories/{candidate.metadata.id}/approve",
            json={"expected_updated_at": candidate.version},
        )
        assert forbidden.status_code == 401

        approved = await client.post(
            f"/ui/api/memories/{candidate.metadata.id}/approve",
            headers={"X-GAM-Action": "dashboard"},
            json={
                "expected_updated_at": candidate.version,
                "visibility": "protected",
                "access_policy": "user_approval",
                "allowed_projects": [],
                "max_permission": "read",
            },
        )
        assert approved.status_code == 200
        assert approved.json()["data"]["status"] == "active"
        assert approved.json()["data"]["visibility"] == "protected"
        assert approved.json()["data"]["allowed_projects"] == ["Alpha"]

        classified = await client.post(
            f"/ui/api/memories/{candidate.metadata.id}/classify",
            headers={"X-GAM-Action": "dashboard"},
            json={
                "expected_updated_at": approved.json()["data"]["version"],
                "visibility": "protected",
                "access_policy": "user_approval",
                "allowed_projects": ["ignored-for-project-scope"],
                "max_permission": "manage",
            },
        )
        assert classified.status_code == 200
        protected = classified.json()["data"]
        assert protected["max_permission"] == "manage"
        assert protected["allowed_projects"] == ["Alpha"]

        invalid_classification = await client.post(
            f"/ui/api/memories/{candidate.metadata.id}/classify",
            headers={"X-GAM-Action": "dashboard"},
            json={
                "expected_updated_at": protected["version"],
                "visibility": "protected",
                "access_policy": "user_approval",
                "allowed_projects": [],
                "max_permission": "technique",
            },
        )
        assert invalid_classification.status_code == 400
        invalid_errors = invalid_classification.json()["error"]["details"]["errors"]
        assert invalid_errors and "ctx" not in invalid_errors[0]

        access_request = container.access.request(
            agent="Claude Code",
            purpose="Investigate stable request identifiers",
            query="stable request identifiers",
            project="Alpha",
            permission="manage",
            duration="task",
        )
        refreshed = (await client.get("/ui/api/bootstrap?project=Alpha")).json()["data"]
        pending = next(item for item in refreshed["access"]["requests"] if item["id"] == access_request["request_id"])
        assert pending["matches"][0]["title"] == "Use durable IDs"
        assert pending["matches"][0]["max_permission"] == "manage"

        granted = await client.post(
            f"/ui/api/access/{access_request['request_id']}/approve",
            headers={"X-GAM-Action": "dashboard"},
            json={"permission": "edit", "duration": "15m", "memory_ids": [candidate.metadata.id]},
        )
        assert granted.status_code == 200
        assert granted.json()["data"]["result"]["grant"]["permission"] == "edit"
        assert granted.json()["data"]["access"]["grants"][0]["scope_count"] == 1

        backup = await client.post("/ui/api/backup", headers={"X-GAM-Action": "dashboard"}, json={})
        assert backup.status_code == 200
        assert await anyio.Path(backup.json()["data"]["path"]).is_file()

    container.database.close()


@pytest.mark.asyncio
async def test_dashboard_json_mutations_fail_closed_on_malformed_or_non_object_payloads(tmp_path: Path) -> None:
    container = build_container(tmp_path / "vault", tmp_path / "state")
    candidate = container.memory.remember(
        MemoryDraft(
            title="Malformed payload target",
            content="A candidate used to verify dashboard input handling.",
            type="fact",
            scope="global",
        )
    )
    sessions = DashboardSessions("http://127.0.0.1:8765")
    app = Starlette(routes=dashboard_routes(container, sessions))

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        launch = sessions.launch(open_browser=False)
        ticket = parse_qs(urlsplit(launch["url"]).query)["ticket"][0]
        assert (await client.get(f"/ui/session?ticket={ticket}", follow_redirects=False)).status_code == 303
        headers = {"X-GAM-Action": "dashboard", "Content-Type": "application/json"}
        endpoints = [
            ("PATCH", f"/ui/api/memories/{candidate.metadata.id}"),
            ("POST", f"/ui/api/memories/{candidate.metadata.id}/classify"),
            ("POST", f"/ui/api/memories/{candidate.metadata.id}/unlock"),
            ("POST", "/ui/api/access/missing/unknown"),
        ]
        for method, endpoint in endpoints:
            malformed = await client.request(method, endpoint, headers=headers, content="{")
            assert malformed.status_code == 400
            assert malformed.json()["error"]["code"] == "NOTE_INVALID"

        non_object = await client.patch(
            f"/ui/api/memories/{candidate.metadata.id}",
            headers={"X-GAM-Action": "dashboard"},
            json=["not", "an", "object"],
        )
        assert non_object.status_code == 400
        assert non_object.json()["error"]["code"] == "NOTE_INVALID"

    container.database.close()


@pytest.mark.asyncio
async def test_dashboard_sealed_unlock_is_one_view_and_open_routes_remain_blocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    container = build_container(tmp_path / "vault", tmp_path / "state")
    candidate = container.memory.remember(
        MemoryDraft(
            title="Owner-only incident details",
            content="Owner-only incident body.",
            type="reference",
            scope="global",
        )
    )
    active = container.memory.approve(candidate.metadata.id, candidate.version)
    sealed = container.memory.update(
        active.metadata.id,
        active.version,
        metadata_patch={"visibility": "sealed", "access_policy": "per_access"},
    )
    opened: list[str] = []
    monkeypatch.setattr("global_memory.dashboard.routes.webbrowser.open", lambda uri: bool(opened.append(uri)))
    sessions = DashboardSessions("http://127.0.0.1:8765")
    app = Starlette(routes=dashboard_routes(container, sessions))

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        invalid_ticket = await client.get("/ui/session?ticket=missing", follow_redirects=False)
        assert invalid_ticket.status_code == 401
        assert invalid_ticket.headers.get("set-cookie") is None

        launch = sessions.launch(open_browser=False)
        ticket = parse_qs(urlsplit(launch["url"]).query)["ticket"][0]
        exchanged = await client.get(f"/ui/session?ticket={ticket}", follow_redirects=False)
        assert exchanged.status_code == 303
        assert "HttpOnly" in exchanged.headers["set-cookie"]
        assert "SameSite=strict" in exchanged.headers["set-cookie"]
        headers = {"X-GAM-Action": "dashboard"}

        for action in ("open-file", "open-obsidian"):
            blocked = await client.post(f"/ui/api/memories/{sealed.metadata.id}/{action}", headers=headers, json={})
            assert blocked.status_code == 403
            assert blocked.json()["error"]["code"] == "ACCESS_APPROVAL_REQUIRED"
        assert opened == []

        unlocked = await client.post(
            f"/ui/api/memories/{sealed.metadata.id}/unlock",
            headers=headers,
            json={"purpose": "Verify incident follow-up"},
        )
        assert unlocked.status_code == 200
        assert unlocked.json()["data"]["title"] == "Owner-only incident details"
        assert unlocked.json()["data"]["body"] == "Owner-only incident body."
        assert any(event["action"] == "sealed_unlocked" for event in container.access.dashboard_state()["events"])

        bootstrap = (await client.get("/ui/api/bootstrap")).json()["data"]
        redacted = next(memory for memory in bootstrap["memories"] if memory["id"] == sealed.metadata.id)
        assert redacted["title"] == "Sealed memory"
        assert redacted["body"] == ""

    container.database.close()
