"""Client-neutral live MCP acceptance used by both integration adapters."""

from __future__ import annotations

import asyncio
import subprocess
import tempfile
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from global_memory.integrations.manager import ClientName, IntegrationManager


@dataclass(frozen=True, slots=True)
class VerificationReport:
    client: ClientName
    ok: bool
    checks: dict[str, bool]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _structured(result: Any) -> dict[str, Any]:
    if not isinstance(result.structuredContent, dict):
        raise RuntimeError("MCP verification result omitted structured content")
    return result.structuredContent


async def verify_client(manager: IntegrationManager, client_name: ClientName) -> VerificationReport:
    """Verify installed artifact plus one shared-daemon isolation/lifecycle smoke flow."""
    install_status = manager.status(client_name)
    checks = {
        "client_executable": bool(install_status["client_available"]),
        "skill_hash": bool(install_status["skill_valid"]),
        "mcp_registration": bool(install_status["mcp_registered"]),
    }
    token = manager.token_file.read_text().strip()
    prefix = uuid.uuid4().hex[:10]
    created: list[tuple[str, str]] = []
    projects: list[str] = []
    try:
        async with (
            httpx.AsyncClient(headers={"Authorization": f"Bearer {token}"}) as http,
            streamable_http_client(manager.endpoint, http_client=http) as (read_stream, write_stream, _),
            ClientSession(read_stream, write_stream) as session,
        ):
            await session.initialize()
            tools = await session.list_tools()
            resources = await session.list_resources()
            templates = await session.list_resource_templates()
            prompts = await session.list_prompts()
            checks["discovery"] = (
                len(tools.tools) == 14
                and len(resources.resources) + len(templates.resourceTemplates) == 10
                and len(prompts.prompts) == 6
            )
            status = await session.call_tool("memory_status", {})
            checks["memory_status"] = not status.isError
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                roots = [root / "alpha", root / "beta"]
                for index, project_root in enumerate(roots):
                    project_root.mkdir()
                    await asyncio.to_thread(subprocess.run, ["git", "init", "-q", str(project_root)], check=True)
                    project = f"verify-{prefix}-{index}"
                    projects.append(project)
                    added = await session.call_tool(
                        "memory_projects",
                        {
                            "request_id": f"verify-project-{prefix}-{index}",
                            "action": "add",
                            "payload": {"name": project, "roots": [str(project_root)]},
                        },
                    )
                    if added.isError:
                        raise RuntimeError("project add failed")
                detected = await session.call_tool(
                    "memory_projects",
                    {"action": "detect", "payload": {"working_directory": str(roots[0])}},
                )
                checks["project_detection"] = (
                    not detected.isError
                    and _structured(detected)["data"]["detection"]["project"]["name"] == projects[0]
                )
                for index, project in enumerate(projects):
                    remembered = await session.call_tool(
                        "memory_remember",
                        {
                            "request_id": f"verify-memory-{prefix}-{index}",
                            "title": f"Verification {index}",
                            "content": f"unique-{prefix}-{index}",
                            "type": "fact",
                            "scope": "project",
                            "project": project,
                        },
                    )
                    data = _structured(remembered)["data"]
                    created.append((data["metadata"]["id"], data["version"]))
                fetched = await session.call_tool("memory_get", {"id": created[0][0]})
                checks["candidate_create_read"] = not fetched.isError
                isolated = await session.call_tool(
                    "memory_search",
                    {
                        "query": f"unique-{prefix}-1",
                        "mode": "keyword",
                        "working_directory": str(roots[0]),
                        "include_candidates": True,
                    },
                )
                checks["project_isolation"] = not _structured(isolated)["data"]["results"]
                for index, (memory_id, version) in enumerate(created):
                    rejected = await session.call_tool(
                        "memory_reject",
                        {
                            "request_id": f"verify-reject-{prefix}-{index}",
                            "id": memory_id,
                            "expected_updated_at": version,
                            "reason": "Integration verification cleanup",
                        },
                    )
                    checks["candidate_cleanup"] = checks.get("candidate_cleanup", True) and not rejected.isError
                for index, project in enumerate(projects):
                    await session.call_tool(
                        "memory_projects",
                        {
                            "request_id": f"verify-deactivate-{prefix}-{index}",
                            "action": "deactivate",
                            "payload": {"name": project},
                        },
                    )
    except Exception:
        checks.setdefault("daemon_connectivity", False)
    else:
        checks["daemon_connectivity"] = True
    return VerificationReport(client=client_name, ok=all(checks.values()), checks=checks)
