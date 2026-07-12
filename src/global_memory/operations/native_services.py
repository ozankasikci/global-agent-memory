"""Native per-user service rendering and lifecycle operations."""

from __future__ import annotations

import os
import plistlib
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from global_memory.errors import ErrorCode, GlobalMemoryError

MANAGED_MARKER = "Managed by global-memory-mcp"


@dataclass(frozen=True, slots=True)
class ServiceFile:
    kind: str
    path: Path
    content: bytes


def render_service_file(kind: str, *, config_file: Path, home: Path, executable: str | None = None) -> ServiceFile:
    """Render launchd or systemd-user configuration without installing it."""
    python = executable or sys.executable
    arguments = [python, "-m", "global_memory.cli", "serve", "--config", str(config_file)]
    if kind == "launchd":
        path = home / "Library/LaunchAgents/com.global-memory.plist"
        payload = {
            "Label": "com.global-memory",
            "ProgramArguments": arguments,
            "RunAtLoad": True,
            "KeepAlive": True,
            "ProcessType": "Background",
        }
        content = plistlib.dumps(payload)
        content = content.replace(b"<dict>", f"<!-- {MANAGED_MARKER} -->\n<dict>".encode(), 1)
        return ServiceFile(kind=kind, path=path, content=content)
    if kind == "systemd":
        path = home / ".config/systemd/user/global-memory.service"
        command = " ".join(shlex.quote(part) for part in arguments)
        content = (
            f"# {MANAGED_MARKER}\n[Unit]\nDescription=Global Agent Memory MCP daemon\n\n"
            f"[Service]\nType=simple\nExecStart={command}\nRestart=on-failure\n\n"
            "[Install]\nWantedBy=default.target\n"
        ).encode()
        return ServiceFile(kind=kind, path=path, content=content)
    raise GlobalMemoryError(ErrorCode.CONFIG_INVALID, "Service kind must be launchd or systemd.")


def install_service(service: ServiceFile) -> Path:
    """Install idempotently, refusing to replace an unmanaged service file."""
    if service.path.exists():
        existing = service.path.read_bytes()
        if MANAGED_MARKER.encode() not in existing:
            raise GlobalMemoryError(
                ErrorCode.INTEGRATION_CONFLICT,
                "An unmanaged service file already exists.",
                details={"path": str(service.path)},
            )
        if existing == service.content:
            return service.path
    service.path.parent.mkdir(parents=True, exist_ok=True)
    service.path.write_bytes(service.content)
    return service.path


def uninstall_service(service: ServiceFile) -> bool:
    """Remove only a service file carrying this product's marker."""
    if not service.path.exists():
        return False
    if MANAGED_MARKER.encode() not in service.path.read_bytes():
        raise GlobalMemoryError(ErrorCode.INTEGRATION_CONFLICT, "The service file is not managed by this product.")
    service.path.unlink()
    return True


def enable_service(service: ServiceFile) -> list[list[str]]:
    """Load and enable a managed per-user service with the native service manager."""
    if not service.path.exists() or MANAGED_MARKER.encode() not in service.path.read_bytes():
        raise GlobalMemoryError(ErrorCode.INTEGRATION_CONFLICT, "The managed service file is not installed.")
    if service.kind == "launchd":
        domain = f"gui/{os.getuid()}"
        commands = [
            ["launchctl", "bootout", f"{domain}/com.global-memory"],
            ["launchctl", "bootstrap", domain, str(service.path)],
        ]
    elif service.kind == "systemd":
        commands = [
            ["systemctl", "--user", "daemon-reload"],
            ["systemctl", "--user", "enable", "--now", "global-memory.service"],
        ]
    else:
        raise GlobalMemoryError(ErrorCode.CONFIG_INVALID, "Service kind must be launchd or systemd.")
    try:
        if service.kind == "launchd":
            subprocess.run(commands[0], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            service_name = f"gui/{os.getuid()}/com.global-memory"
            unload_deadline = time.monotonic() + 5
            while True:
                status = subprocess.run(
                    ["launchctl", "print", service_name],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                if status.returncode != 0:
                    break
                if time.monotonic() >= unload_deadline:
                    raise subprocess.TimeoutExpired(commands[0], 5)
                time.sleep(0.05)
            bootstrap_deadline = time.monotonic() + 5
            while True:
                bootstrap = subprocess.run(
                    commands[1], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                if bootstrap.returncode == 0:
                    break
                if time.monotonic() >= bootstrap_deadline:
                    raise subprocess.CalledProcessError(bootstrap.returncode, commands[1])
                time.sleep(0.1)
        else:
            for command in commands:
                subprocess.run(command, check=True)
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise GlobalMemoryError(
            ErrorCode.INTERNAL_ERROR,
            "The native user-service manager could not enable Global Agent Memory.",
            details={"kind": service.kind},
            remediation="Inspect the installed service file, enable it manually, then run doctor.",
        ) from exc
    return commands


def disable_service(service: ServiceFile) -> list[list[str]]:
    """Stop and disable a managed per-user service before uninstalling its file."""
    if not service.path.exists() or MANAGED_MARKER.encode() not in service.path.read_bytes():
        raise GlobalMemoryError(ErrorCode.INTEGRATION_CONFLICT, "The managed service file is not installed.")
    if service.kind == "launchd":
        commands = [["launchctl", "bootout", f"gui/{os.getuid()}/com.global-memory"]]
    elif service.kind == "systemd":
        commands = [
            ["systemctl", "--user", "disable", "--now", "global-memory.service"],
            ["systemctl", "--user", "daemon-reload"],
        ]
    else:
        raise GlobalMemoryError(ErrorCode.CONFIG_INVALID, "Service kind must be launchd or systemd.")
    try:
        for command in commands:
            subprocess.run(command, check=False)
    except OSError as exc:
        raise GlobalMemoryError(
            ErrorCode.INTERNAL_ERROR,
            "The native user-service manager could not disable Global Agent Memory.",
            details={"kind": service.kind},
            remediation="Stop the user service manually before removing the managed service file.",
        ) from exc
    return commands
