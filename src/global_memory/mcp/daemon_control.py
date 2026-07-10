"""Safe lifecycle control for the managed per-user daemon process."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import httpx

from global_memory.config import GlobalMemorySettings, PlatformPaths
from global_memory.errors import ErrorCode, GlobalMemoryError


@dataclass(frozen=True, slots=True)
class DaemonState:
    pid: int
    instance_id: str
    endpoint: str


def _state_file(paths: PlatformPaths) -> Path:
    return paths.runtime_dir / "daemon.json"


def _read_state(paths: PlatformPaths) -> DaemonState | None:
    try:
        value = json.loads(_state_file(paths).read_text())
        return DaemonState(pid=int(value["pid"]), instance_id=value["instance_id"], endpoint=value["endpoint"])
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None


def _health(state: DaemonState, *, timeout: float = 0.25) -> bool:
    try:
        response = httpx.get(state.endpoint.removesuffix("/mcp/") + "/health/ready", timeout=timeout)
        payload: Any = response.json()
        return (
            response.status_code == 200
            and isinstance(payload, dict)
            and payload.get("instance_id") == state.instance_id
        )
    except (httpx.HTTPError, ValueError):
        return False


def daemon_status(paths: PlatformPaths) -> DaemonState | None:
    """Return the verified managed daemon state, never trusting a PID alone."""
    state = _read_state(paths)
    return state if state is not None and _health(state) else None


def start_daemon(settings: GlobalMemorySettings, paths: PlatformPaths, *, timeout: float = 10) -> DaemonState:
    """Start one detached daemon and wait until its matching health endpoint is ready."""
    existing = daemon_status(paths)
    if existing is not None:
        return existing
    paths.runtime_dir.mkdir(parents=True, exist_ok=True)
    paths.data_dir.mkdir(parents=True, exist_ok=True)
    paths.log_dir.mkdir(parents=True, exist_ok=True)
    instance_id = str(uuid.uuid4())
    endpoint = f"http://{settings.mcp.host}:{settings.mcp.port}/mcp/"
    log_path = paths.log_dir / "daemon.log"
    command = [
        sys.executable,
        "-m",
        "global_memory.mcp.daemon",
        "--vault",
        str(settings.vault_path),
        "--state",
        str(paths.data_dir),
        "--token-file",
        str(paths.auth_token),
        "--host",
        settings.mcp.host,
        "--port",
        str(settings.mcp.port),
        "--max-request-bytes",
        str(settings.mcp.max_request_bytes),
        "--instance-id",
        instance_id,
        "--debounce-ms",
        str(settings.index.debounce_ms),
    ]
    for pattern in settings.index.excluded_globs:
        command.extend(["--exclude", pattern])
    if not settings.index.watch:
        command.append("--no-watch")
    with log_path.open("a") as log:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            start_new_session=True,
        )
    state = DaemonState(pid=process.pid, instance_id=instance_id, endpoint=endpoint)
    state_path = _state_file(paths)
    state_path.write_text(json.dumps(asdict(state), sort_keys=True) + "\n")
    state_path.chmod(0o600)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            state_path.unlink(missing_ok=True)
            raise GlobalMemoryError(
                ErrorCode.DAEMON_UNAVAILABLE,
                "The daemon exited before becoming ready.",
                details={"log_path": str(log_path)},
                remediation="Inspect the daemon log and validate the configuration.",
            )
        if _health(state):
            return state
        time.sleep(0.05)
    process.terminate()
    state_path.unlink(missing_ok=True)
    raise GlobalMemoryError(
        ErrorCode.DAEMON_UNAVAILABLE,
        "The daemon did not become ready before the startup timeout.",
        details={"log_path": str(log_path)},
    )


def stop_daemon(paths: PlatformPaths, *, timeout: float = 5) -> bool:
    """Stop only a process whose instance identity matches its health endpoint."""
    state = daemon_status(paths)
    if state is None:
        _state_file(paths).unlink(missing_ok=True)
        return False
    os.kill(state.pid, signal.SIGTERM)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _health(state):
            _state_file(paths).unlink(missing_ok=True)
            return True
        time.sleep(0.05)
    raise GlobalMemoryError(
        ErrorCode.DAEMON_UNAVAILABLE,
        "The managed daemon did not stop before the timeout.",
        retryable=True,
        remediation="Retry the stop command; the process was not force-killed.",
    )
