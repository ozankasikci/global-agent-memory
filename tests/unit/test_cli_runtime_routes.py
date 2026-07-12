from __future__ import annotations

from typing import Any

import pytest
from typer.testing import CliRunner

import global_memory.cli as cli
from global_memory.domain.models import SUPPORTED_MEMORY_TYPES


def test_remember_help_enumerates_supported_memory_types() -> None:
    result = CliRunner().invoke(cli.app, ["remember", "--help"])

    assert result.exit_code == 0
    for memory_type in SUPPORTED_MEMORY_TYPES:
        assert memory_type in result.stdout


def test_every_runtime_cli_command_routes_to_a_frozen_mcp_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    def record(name: str, arguments: dict[str, Any], **_options: Any) -> None:
        calls.append((name, arguments))

    monkeypatch.setattr(cli, "_call_runtime", record)
    invocations = [
        ["status"],
        ["search", "query"],
        ["context", "task"],
        ["remember", "Title", "Body", "--type", "fact", "--scope", "global"],
        ["get", "mem_a"],
        ["approve", "mem_a"],
        ["reject", "mem_a", "--reason", "bad"],
        ["update", "mem_a", "--expected-updated-at", "v1"],
        ["supersede", "mem_a", "mem_b", "--reason", "new"],
        ["archive", "mem_a", "--reason", "old"],
        ["reindex", "--full"],
        ["project", "list"],
    ]
    runner = CliRunner()
    for arguments in invocations:
        result = runner.invoke(cli.app, arguments)
        assert result.exit_code == 0, result.output

    assert {name for name, _ in calls} == {
        "memory_status",
        "memory_search",
        "memory_context",
        "memory_remember",
        "memory_get",
        "memory_approve",
        "memory_reject",
        "memory_update",
        "memory_supersede",
        "memory_archive",
        "memory_reindex",
        "memory_projects",
    }


def test_dashboard_command_routes_through_mcp_and_reports_launch_url(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    async def call(_endpoint, _token, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        calls.append((name, arguments))
        return {
            "ok": True,
            "data": {
                "url": "http://127.0.0.1:8765/ui/session?ticket=test",
                "opened": True,
                "expires_in_seconds": 60,
            },
        }

    monkeypatch.setattr(cli, "_runtime_target", lambda *_args: ("http://localhost/mcp", None))
    monkeypatch.setattr(cli, "call_http_tool", call)
    result = CliRunner().invoke(cli.app, ["dashboard"])

    assert result.exit_code == 0, result.output
    assert "Dashboard opened" in result.output
    assert calls == [("memory_dashboard_open", {"open_browser": True})]
