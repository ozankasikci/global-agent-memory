from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import anyio
import httpx
import pytest
from starlette.applications import Starlette

from global_memory.dashboard import DashboardSessions, dashboard_routes
from global_memory.domain.models import MemoryDraft
from global_memory.mcp.server import build_container
from global_memory.projects.models import ProjectDraft


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
    sessions = DashboardSessions("http://127.0.0.1:8765")
    app = Starlette(routes=dashboard_routes(container, sessions))

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
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
        assert data["project_stats"]["Alpha"]["candidates"] == 1
        assert data["candidates"][0]["id"] == candidate.metadata.id
        assert data["candidates"][0]["evidence"] == "Verified in tests."

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
