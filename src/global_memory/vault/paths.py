"""Canonical routing and confinement for all Vault paths."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from global_memory.domain.models import MemoryMetadata, MemoryScope, MemoryStatus
from global_memory.errors import ErrorCode, GlobalMemoryError

TYPE_FOLDERS = {
    "decision": "Decisions",
    "fact": "Facts",
    "solution": "Problems and Solutions",
    "session_summary": "Session Summaries",
}

UNMANAGED_DIRECTORIES = {"Templates", "Dashboards"}
UNMANAGED_ROOT_FILES = {"README.md"}


def safe_component(value: str) -> str:
    """Create a readable path component without separators or traversal."""
    normalized = unicodedata.normalize("NFKC", value).strip()
    normalized = re.sub(r"[/:\\]+", "-", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = normalized.strip(". ")
    return normalized[:100] or "Untitled"


def note_filename(metadata: MemoryMetadata) -> str:
    short_id = metadata.id.removeprefix("mem_")[:8]
    return f"{safe_component(metadata.title)}--{short_id}.md"


def canonical_path(metadata: MemoryMetadata) -> Path:
    """Return the deterministic Vault-relative lifecycle destination."""
    filename = note_filename(metadata)
    if metadata.status is MemoryStatus.CANDIDATE:
        return Path("00 Inbox") / "AI Candidates" / filename
    if metadata.status is MemoryStatus.REJECTED:
        return Path("90 Archive") / "Rejected" / filename
    if metadata.status is MemoryStatus.ARCHIVED:
        return Path("90 Archive") / filename
    if metadata.scope is MemoryScope.PROJECT:
        folder = TYPE_FOLDERS.get(metadata.type, f"{safe_component(metadata.type).title()}s")
        return Path("20 Projects") / safe_component(metadata.project or "Unknown Project") / folder / filename
    if metadata.scope is MemoryScope.ORGANIZATION:
        return Path("15 Organization") / filename
    if metadata.scope is MemoryScope.SESSION or metadata.type == "session_summary":
        return Path("70 Session Summaries") / filename
    if metadata.type == "preference":
        return Path("10 Global") / "Preferences" / filename
    if metadata.type == "convention":
        return Path("10 Global") / "Conventions" / filename
    if metadata.type == "decision":
        return Path("30 Decisions") / filename
    if metadata.type == "solution":
        return Path("40 Problems and Solutions") / filename
    if metadata.type == "entity":
        return Path("50 Entities") / filename
    return Path("10 Global") / "Reusable Knowledge" / filename


def safe_vault_path(vault: Path, relative: Path) -> Path:
    """Resolve a relative path and reject traversal, absolute paths, and symlink escapes."""
    vault_resolved = vault.resolve()
    if relative.is_absolute() or ".." in relative.parts:
        raise GlobalMemoryError(
            ErrorCode.PATH_OUTSIDE_VAULT,
            "The requested path is outside the configured Vault.",
            details={"path": str(relative)},
            remediation="Use a normalized path relative to the configured Vault.",
        )
    candidate = vault / relative
    resolved = candidate.resolve(strict=False)
    if not resolved.is_relative_to(vault_resolved):
        raise GlobalMemoryError(
            ErrorCode.PATH_OUTSIDE_VAULT,
            "The requested path escapes the configured Vault.",
            details={"path": str(relative)},
            remediation="Remove traversal or symlink components and use a Vault-relative path.",
        )
    return candidate


def is_managed_memory_path(relative: Path) -> bool:
    """Distinguish canonical memory notes from Obsidian-facing support assets."""
    if relative.suffix.casefold() != ".md" or not relative.parts:
        return False
    if any(part.startswith(".") for part in relative.parts):
        return False
    if relative.name in UNMANAGED_ROOT_FILES or relative.parts[0] in UNMANAGED_DIRECTORIES:
        return False
    return not (
        len(relative.parts) >= 3 and relative.parts[0] == "20 Projects" and relative.name == "Project Overview.md"
    )
