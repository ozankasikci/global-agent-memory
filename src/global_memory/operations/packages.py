"""Installed-package upgrade and rollback operations."""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys

from global_memory.errors import ErrorCode, GlobalMemoryError


def package_change(version: str | None = None) -> list[str]:
    """Upgrade or roll back the active Python environment using its own interpreter."""
    requirement = "global-memory-mcp" + (f"=={version}" if version else "")
    if importlib.util.find_spec("pip") is not None:
        command = [sys.executable, "-m", "pip", "install", "--upgrade", requirement]
    elif uv := shutil.which("uv"):
        command = [uv, "pip", "install", "--python", sys.executable, "--upgrade", requirement]
    else:
        raise GlobalMemoryError(
            ErrorCode.INTERNAL_ERROR,
            "Neither pip nor uv is available to change the installed Global Agent Memory version.",
            remediation="Use the same environment manager that installed global-memory-mcp, then run doctor.",
        )
    try:
        subprocess.run(command, check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise GlobalMemoryError(
            ErrorCode.INTERNAL_ERROR,
            "The package manager could not change the installed Global Agent Memory version.",
            details={"command": command[:-1], "requirement": requirement},
            remediation="Use the same environment manager that installed global-memory-mcp, then run doctor.",
        ) from exc
    return command
