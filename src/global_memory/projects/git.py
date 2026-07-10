"""Git root discovery and transport-neutral remote normalization."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from urllib.parse import urlparse


def normalize_git_remote(remote: str) -> str:
    """Normalize common SCP, SSH, HTTP, and HTTPS forms to host/path."""
    value = remote.strip().rstrip("/")
    scp = re.fullmatch(r"(?:[^@/]+@)?([^:/]+):(.+)", value)
    if scp and "://" not in value:
        host = scp.group(1)
        path = scp.group(2)
    else:
        parsed = urlparse(value)
        if parsed.scheme and parsed.hostname:
            host = parsed.hostname
            if parsed.port:
                host = f"{host}:{parsed.port}"
            path = parsed.path.lstrip("/")
        else:
            return str(Path(value).expanduser().resolve()).rstrip("/").removesuffix(".git")
    return f"{host}/{path.removesuffix('.git')}".strip("/").casefold()


def nearest_git_root(working_directory: Path) -> Path | None:
    """Find the closest parent containing a Git directory or worktree file."""
    current = working_directory.expanduser().resolve()
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def origin_remote(git_root: Path) -> str | None:
    """Read origin without invoking a shell or leaking configuration contents."""
    result = subprocess.run(
        ["git", "-C", str(git_root), "config", "--get", "remote.origin.url"],
        check=False,
        capture_output=True,
        text=True,
        timeout=3,
    )
    value = result.stdout.strip()
    return value if result.returncode == 0 and value else None
