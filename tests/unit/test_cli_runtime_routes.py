from __future__ import annotations

from typing import Any

import pytest
from typer.testing import CliRunner

import global_memory.cli as cli


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
