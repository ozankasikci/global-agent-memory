from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import global_memory.mcp.local_runtime as runtime
from global_memory.config import GlobalMemorySettings, PlatformPaths


def _paths(tmp_path: Path) -> PlatformPaths:
    return PlatformPaths(
        config_dir=tmp_path / "config",
        data_dir=tmp_path / "data",
        log_dir=tmp_path / "logs",
        runtime_dir=tmp_path / "run",
    )


@pytest.mark.asyncio
async def test_runtime_prefers_a_ready_daemon(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    async def ready(_endpoint: str) -> bool:
        return True

    async def call(_endpoint: str, _token: Path, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        calls.append((name, arguments))
        return {"contract_version": 1, "ok": True, "data": {"transport": "streamable-http"}}

    monkeypatch.setattr(runtime, "daemon_ready", ready)
    monkeypatch.setattr(runtime, "call_http_tool", call)
    result = await runtime.call_runtime_tool(
        "http://127.0.0.1:8765/mcp/",
        tmp_path / "token",
        "memory_status",
        {},
        paths=_paths(tmp_path),
    )

    assert result["data"]["transport"] == "streamable-http"
    assert calls == [("memory_status", {})]


@pytest.mark.asyncio
async def test_runtime_falls_back_to_local_mcp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = _paths(tmp_path)
    settings = GlobalMemorySettings(vault_path=tmp_path / "vault", embeddings={"enabled": False})

    async def unavailable(_endpoint: str) -> bool:
        return False

    monkeypatch.setattr(runtime, "daemon_ready", unavailable)
    monkeypatch.setattr(runtime, "load_settings", lambda _path: settings)
    result = await runtime.call_runtime_tool(
        "http://127.0.0.1:65530/mcp/",
        tmp_path / "token",
        "memory_status",
        {},
        paths=paths,
    )

    assert result["ok"] is True
    assert result["data"]["transport"] == "stdio-direct"
    assert paths.database.exists()
