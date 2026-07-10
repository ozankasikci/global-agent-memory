"""Safe, idempotent Vault and local-state initialization."""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path

from global_memory.config import GlobalMemorySettings, PlatformPaths, render_config
from global_memory.errors import ErrorCode, GlobalMemoryError
from global_memory.vault.obsidian import install_obsidian_assets

MANAGED_DIRECTORIES = (
    "00 Inbox/AI Candidates",
    "10 Global/Preferences",
    "10 Global/Conventions",
    "10 Global/Reusable Knowledge",
    "15 Organization",
    "20 Projects",
    "30 Decisions",
    "40 Problems and Solutions",
    "50 Entities/People",
    "50 Entities/Organizations",
    "50 Entities/Technologies",
    "70 Session Summaries",
    "90 Archive",
    "Templates",
    "Dashboards",
)

VAULT_README = """# Global Memory

This Obsidian Vault is the durable source of truth for Global Memory. Markdown and YAML may be inspected and edited
here. Generated databases, vectors, tokens, locks, and logs are stored outside this Vault and can be rebuilt.

AI-created notes enter `00 Inbox/AI Candidates/` for review. Lifecycle changes should use the Global Memory MCP tools
or CLI so identity, audit history, and indexes remain consistent.

Open [[Dashboards/Global Memory]] for review queues, active knowledge, and lifecycle history. Project-scoped memories
link to a generated project overview. Existing templates, dashboards, and overview files are never overwritten.
"""


@dataclass(frozen=True, slots=True)
class InitializationResult:
    """Paths and creation state safe to display to the user."""

    vault_path: Path
    config_file: Path
    created: bool


def _create_private_token(path: Path) -> None:
    if path.exists():
        os.chmod(path, 0o600)
        return
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(path, flags, 0o600)
    try:
        os.write(descriptor, (secrets.token_urlsafe(48) + "\n").encode())
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.chmod(path, 0o600)


def initialize(settings: GlobalMemorySettings, paths: PlatformPaths) -> InitializationResult:
    """Create managed directories and protected local files without overwriting user content."""
    vault = settings.vault_path.expanduser()
    if not vault.is_absolute():
        raise GlobalMemoryError(
            ErrorCode.CONFIG_INVALID,
            "The Vault path must be absolute.",
            details={"field": "vault_path"},
            remediation="Choose an absolute path for the Obsidian Vault.",
        )
    if vault.exists() and not vault.is_dir():
        raise GlobalMemoryError(
            ErrorCode.VAULT_NOT_WRITABLE,
            "The configured Vault path is not a directory.",
            details={"path": str(vault)},
            remediation="Choose a writable directory path.",
        )
    created = not vault.exists()
    try:
        vault.mkdir(parents=True, exist_ok=True)
        for relative in MANAGED_DIRECTORIES:
            (vault / relative).mkdir(parents=True, exist_ok=True)
        readme = vault / "README.md"
        if not readme.exists():
            readme.write_text(VAULT_README)
        install_obsidian_assets(vault)
        paths.config_dir.mkdir(parents=True, exist_ok=True)
        paths.data_dir.mkdir(parents=True, exist_ok=True)
        paths.log_dir.mkdir(parents=True, exist_ok=True)
        paths.runtime_dir.mkdir(parents=True, exist_ok=True)
        if not paths.config_file.exists():
            paths.config_file.write_text(render_config(settings))
        _create_private_token(paths.auth_token)
    except OSError as exc:
        raise GlobalMemoryError(
            ErrorCode.VAULT_NOT_WRITABLE,
            "Global Memory initialization could not write a required path.",
            details={"path": str(getattr(exc, "filename", vault)), "reason": str(exc)},
            remediation="Check ownership and permissions, then retry initialization.",
        ) from exc
    return InitializationResult(vault_path=vault, config_file=paths.config_file, created=created)
