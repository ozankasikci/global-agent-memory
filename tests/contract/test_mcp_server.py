from __future__ import annotations

import json
from pathlib import Path

import pytest
from mcp import types
from mcp.shared.memory import create_connected_server_and_client_session

from global_memory.mcp.server import build_container, create_mcp_server

pytestmark = [pytest.mark.contract, pytest.mark.asyncio]
ROOT = Path(__file__).resolve().parents[2]
DISCOVERY = json.loads((ROOT / "contracts/mcp/v1/discovery.json").read_text())


async def call(session, name: str, arguments: dict[str, object] | None = None) -> dict[str, object]:
    result = await session.call_tool(name, arguments or {})
    assert not result.isError, result.content
    assert result.structuredContent
    assert result.structuredContent["contract_version"] == 1
    assert result.structuredContent["ok"] is True
    return result.structuredContent["data"]


async def test_official_client_discovery_exactly_matches_frozen_v1(tmp_path: Path) -> None:
    server = create_mcp_server(build_container(tmp_path / "vault", tmp_path / "state", transport="direct"))
    async with create_connected_server_and_client_session(server) as session:
        tools = (await session.list_tools()).tools
        expected_tools = {item["name"]: item for item in DISCOVERY["tools"]}
        assert {tool.name for tool in tools} == set(expected_tools)
        for tool in tools:
            expected = expected_tools[tool.name]
            assert tool.description == expected["description"]
            assert tool.inputSchema == expected["inputSchema"]
            assert tool.outputSchema == expected["outputSchema"]

        resources = (await session.list_resources()).resources
        templates = (await session.list_resource_templates()).resourceTemplates
        discovered_uris = {str(resource.uri) for resource in resources} | {
            template.uriTemplate for template in templates
        }
        assert discovered_uris == {item["uriTemplate"] for item in DISCOVERY["resources"]}

        prompts = (await session.list_prompts()).prompts
        expected_prompts = {item["name"]: item for item in DISCOVERY["prompts"]}
        assert {prompt.name for prompt in prompts} == set(expected_prompts)
        for prompt in prompts:
            expected = expected_prompts[prompt.name]
            assert prompt.description == expected["description"]
            assert [argument.model_dump(exclude_none=True) for argument in prompt.arguments or []] == expected[
                "arguments"
            ]


async def test_dashboard_open_uses_daemon_launcher(tmp_path: Path) -> None:
    container = build_container(tmp_path / "vault", tmp_path / "state", transport="direct")
    calls: list[bool] = []

    def launch(open_browser: bool) -> dict[str, object]:
        calls.append(open_browser)
        return {"url": "http://127.0.0.1:8765/ui/session?ticket=test", "opened": open_browser, "expires_in_seconds": 60}

    container.dashboard_launcher = launch
    server = create_mcp_server(container)
    async with create_connected_server_and_client_session(server) as session:
        data = await call(session, "memory_dashboard_open", {"open_browser": False})
        assert data["url"].startswith("http://127.0.0.1:8765/ui/session")
        assert data["opened"] is False
        assert calls == [False]


async def test_every_mandatory_tool_through_official_client(tmp_path: Path) -> None:
    container = build_container(tmp_path / "vault", tmp_path / "state", transport="direct")
    server = create_mcp_server(container)
    async with create_connected_server_and_client_session(server) as session:
        status = await call(session, "memory_status")
        assert status["contract_version"] == 1 and status["transport"] == "direct"

        await call(
            session,
            "memory_projects",
            {
                "action": "add",
                "request_id": "project-add",
                "payload": {"name": "Alpha", "roots": [str(tmp_path / "alpha")]},
            },
        )
        projects = await call(session, "memory_projects", {"action": "list"})
        assert projects["projects"][0]["name"] == "Alpha"

        remembered = await call(
            session,
            "memory_remember",
            {
                "request_id": "remember-1",
                "title": "Retry decision",
                "content": "# Summary\n\nUse stable request identifiers.\n",
                "type": "decision",
                "scope": "project",
                "project": "Alpha",
                "tags": ["retry"],
            },
        )
        memory_id = remembered["metadata"]["id"]
        replay = await call(
            session,
            "memory_remember",
            {
                "request_id": "remember-1",
                "title": "Retry decision",
                "content": "# Summary\n\nUse stable request identifiers.\n",
                "type": "decision",
                "scope": "project",
                "project": "Alpha",
                "tags": ["retry"],
            },
        )
        assert replay["metadata"]["id"] == memory_id

        fetched = await call(session, "memory_get", {"id": memory_id})
        updated = await call(
            session,
            "memory_update",
            {
                "request_id": "update-1",
                "id": memory_id,
                "expected_updated_at": fetched["version"],
                "section_patch": {"Summary": "Use durable request identifiers."},
            },
        )
        approved = await call(
            session,
            "memory_approve",
            {
                "request_id": "approve-1",
                "id": memory_id,
                "expected_updated_at": updated["version"],
                "destination_override": "20 Projects/Alpha/Decisions/Retry decision.md",
            },
        )
        assert approved["metadata"]["status"] == "active"

        search = await call(
            session,
            "memory_search",
            {"query": "durable request", "project": "Alpha", "mode": "keyword"},
        )
        assert search["results"][0]["memory_id"] == memory_id
        context = await call(session, "memory_context", {"task": "durable request", "project": "Alpha"})
        assert context["items"][0]["memory_id"] == memory_id
        opened = await call(session, "memory_open", {"id": memory_id})
        assert opened["obsidian_uri"].startswith("obsidian://open")
        tags = await call(session, "memory_tags", {"project": "Alpha"})
        assert tags["tags"][0]["tag"] == "retry"

        rejected_candidate = await call(
            session,
            "memory_remember",
            {
                "request_id": "remember-reject",
                "title": "Rejected",
                "content": "Unverified candidate.",
                "type": "fact",
                "scope": "project",
                "project": "Alpha",
            },
        )
        rejected = await call(
            session,
            "memory_reject",
            {
                "request_id": "reject-1",
                "id": rejected_candidate["metadata"]["id"],
                "reason": "Unverified",
            },
        )
        assert rejected["metadata"]["status"] == "rejected"

        replacement = await call(
            session,
            "memory_remember",
            {
                "request_id": "replacement",
                "title": "Replacement decision",
                "content": "Use UUID request identifiers.",
                "type": "decision",
                "scope": "project",
                "project": "Alpha",
            },
        )
        superseded = await call(
            session,
            "memory_supersede",
            {
                "request_id": "supersede-1",
                "old_id": memory_id,
                "replacement_id": replacement["metadata"]["id"],
                "reason": "More precise",
            },
        )
        assert superseded["old"]["metadata"]["status"] == "superseded"
        archived = await call(
            session,
            "memory_archive",
            {
                "request_id": "archive-1",
                "id": superseded["replacement"]["metadata"]["id"],
                "reason": "Test cleanup",
            },
        )
        assert archived["metadata"]["status"] == "archived"
        reindexed = await call(session, "memory_reindex", {"request_id": "reindex-1", "full": True})
        assert reindexed["indexed"] >= 1


async def test_structured_errors_resources_and_prompts_through_protocol(tmp_path: Path) -> None:
    container = build_container(tmp_path / "vault", tmp_path / "state", transport="direct")
    server = create_mcp_server(container)
    async with create_connected_server_and_client_session(server) as session:
        invalid = await session.call_tool("memory_search", {})
        assert invalid.isError and invalid.structuredContent
        assert invalid.structuredContent["error"]["code"] == "NOTE_INVALID"

        traversal = await session.call_tool("memory_reindex", {"request_id": "traversal", "paths": ["../outside.md"]})
        assert traversal.isError and traversal.structuredContent
        assert traversal.structuredContent["error"]["code"] == "PATH_OUTSIDE_VAULT"

        status_resource = await session.read_resource(types.AnyUrl("memory://v1/status"))
        envelope = json.loads(status_resource.contents[0].text)
        assert envelope["ok"] and envelope["contract_version"] == 1

        prompt = await session.get_prompt("prepare_project_context", {"task": "Implement retries", "project": "Alpha"})
        text = prompt.messages[0].content.text
        assert "memory_context" in text
        assert "Alpha" in text
        assert "Do not write memory automatically" in text


async def test_every_resource_and_prompt_is_callable_through_official_client(tmp_path: Path) -> None:
    container = build_container(tmp_path / "vault", tmp_path / "state", transport="direct")
    server = create_mcp_server(container)
    async with create_connected_server_and_client_session(server) as session:
        await call(
            session,
            "memory_projects",
            {"action": "add", "request_id": "project", "payload": {"name": "Alpha"}},
        )
        candidate = await call(
            session,
            "memory_remember",
            {
                "request_id": "candidate",
                "title": "Candidate",
                "content": "Candidate project fact.",
                "type": "fact",
                "scope": "project",
                "project": "Alpha",
            },
        )
        memory_id = candidate["metadata"]["id"]
        resource_uris = [
            "memory://v1/status",
            "memory://v1/projects",
            "memory://v1/project/Alpha",
            "memory://v1/project/Alpha/recent",
            "memory://v1/project/Alpha/decisions",
            "memory://v1/project/Alpha/open-problems",
            f"memory://v1/note/{memory_id}",
            "memory://v1/candidates",
            "memory://v1/recent",
            "memory://v1/tags",
        ]
        for uri in resource_uris:
            result = await session.read_resource(types.AnyUrl(uri))
            envelope = json.loads(result.contents[0].text)
            assert envelope["contract_version"] == 1 and envelope["ok"], uri

        for prompt in DISCOVERY["prompts"]:
            arguments = {
                argument["name"]: {
                    "task": "Implement retries",
                    "project": "Alpha",
                    "query": "VERSION_CONFLICT",
                    "working_directory": str(tmp_path),
                    "limit": "10",
                }.get(argument["name"], "value")
                for argument in prompt["arguments"]
                if argument["required"]
            }
            result = await session.get_prompt(prompt["name"], arguments)
            assert result.messages and result.description == prompt["description"]


async def test_protocol_project_detection_prevents_cross_repository_leakage(tmp_path: Path) -> None:
    alpha_root = tmp_path / "alpha"
    beta_root = tmp_path / "beta"
    alpha_root.mkdir()
    beta_root.mkdir()
    server = create_mcp_server(build_container(tmp_path / "vault", tmp_path / "state", transport="direct"))
    async with create_connected_server_and_client_session(server) as session:
        for name, root in (("Alpha", alpha_root), ("Beta", beta_root)):
            await call(
                session,
                "memory_projects",
                {
                    "action": "add",
                    "request_id": f"project-{name}",
                    "payload": {"name": name, "roots": [str(root)]},
                },
            )
            candidate = await call(
                session,
                "memory_remember",
                {
                    "request_id": f"remember-{name}",
                    "title": f"{name} retry policy",
                    "content": f"{name} uses isolated retry policy.",
                    "type": "fact",
                    "scope": "project",
                    "working_directory": str(root),
                },
            )
            await call(
                session,
                "memory_approve",
                {
                    "request_id": f"approve-{name}",
                    "id": candidate["metadata"]["id"],
                    "expected_updated_at": candidate["version"],
                },
            )
        alpha = await call(
            session,
            "memory_search",
            {"query": "isolated retry", "working_directory": str(alpha_root), "mode": "keyword"},
        )
        assert [result["project"] for result in alpha["results"]] == ["Alpha"]
