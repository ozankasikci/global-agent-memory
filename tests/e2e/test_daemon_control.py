from __future__ import annotations

import asyncio
import socket
from pathlib import Path

import httpx
import pytest

from global_memory.config import EmbeddingSettings, GlobalMemorySettings, MCPSettings, PlatformPaths
from global_memory.mcp.daemon_control import daemon_status, start_daemon, stop_daemon
from global_memory.mcp.local_runtime import call_local_tool
from global_memory.vault.initialize import initialize

pytestmark = pytest.mark.e2e


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_managed_daemon_start_status_and_stop(tmp_path: Path) -> None:
    paths = PlatformPaths(
        config_dir=tmp_path / "config",
        data_dir=tmp_path / "data",
        log_dir=tmp_path / "logs",
        runtime_dir=tmp_path / "run",
    )
    paths.config_dir.mkdir()
    paths.auth_token.write_text("managed-test-token\n")
    paths.auth_token.chmod(0o600)
    settings = GlobalMemorySettings(
        vault_path=tmp_path / "vault",
        mcp=MCPSettings(port=_free_port()),
    )

    started = start_daemon(settings, paths)
    try:
        assert daemon_status(paths) == started
        assert start_daemon(settings, paths) == started
    finally:
        assert stop_daemon(paths)
    assert daemon_status(paths) is None
    assert not stop_daemon(paths)


def test_daemonless_dashboard_request_starts_authenticated_server_on_demand(tmp_path: Path) -> None:
    paths = PlatformPaths(
        config_dir=tmp_path / "config",
        data_dir=tmp_path / "data",
        log_dir=tmp_path / "logs",
        runtime_dir=tmp_path / "run",
    )
    settings = GlobalMemorySettings(
        vault_path=tmp_path / "vault",
        mcp=MCPSettings(port=_free_port()),
        embeddings=EmbeddingSettings(enabled=False),
    )
    initialize(settings, paths)
    endpoint = f"http://127.0.0.1:{settings.mcp.port}/mcp/"

    try:
        result = asyncio.run(
            call_local_tool(
                settings,
                paths,
                endpoint=endpoint,
                token_file=paths.auth_token,
                name="memory_dashboard_open",
                arguments={"open_browser": False},
            )
        )
        assert result["ok"] is True
        assert result["data"]["opened"] is False
        response = httpx.get(result["data"]["url"], follow_redirects=True)
        assert response.status_code == 200
        assert "/ui/" in str(response.url)
        assert daemon_status(paths) is not None
    finally:
        stop_daemon(paths)
