from __future__ import annotations

import socket
from pathlib import Path

import pytest

from global_memory.config import GlobalMemorySettings, MCPSettings, PlatformPaths
from global_memory.mcp.daemon_control import daemon_status, start_daemon, stop_daemon

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
