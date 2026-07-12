"""Vault backup and restore operations."""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

from global_memory.errors import ErrorCode, GlobalMemoryError


def backup_vault(vault: Path, destination: Path) -> Path:
    """Create a self-describing archive of the canonical Vault only."""
    if not vault.is_dir():
        raise GlobalMemoryError(ErrorCode.VAULT_NOT_FOUND, "The configured Vault does not exist.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, str] = {}
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(item for item in vault.rglob("*") if item.is_file()):
            relative = path.relative_to(vault).as_posix()
            content = path.read_bytes()
            archive.writestr(relative, content)
            manifest[relative] = hashlib.sha256(content).hexdigest()
        archive.writestr(".global-memory-backup.json", json.dumps({"files": manifest}, sort_keys=True))
    return destination


def restore_vault(archive_path: Path, vault: Path) -> int:
    """Restore only into an empty destination and reject ZIP traversal."""
    if vault.exists() and any(vault.iterdir()):
        raise GlobalMemoryError(
            ErrorCode.VAULT_NOT_WRITABLE,
            "Restore requires an empty destination so existing notes cannot be overwritten.",
            remediation="Move the existing Vault aside or restore to a new absolute path.",
        )
    vault.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path) as archive:
        try:
            manifest = json.loads(archive.read(".global-memory-backup.json"))["files"]
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise GlobalMemoryError(ErrorCode.NOTE_INVALID, "The backup manifest is missing or invalid.") from exc
        names = [name for name in archive.namelist() if name != ".global-memory-backup.json"]
        if not isinstance(manifest, dict) or set(names) != set(manifest):
            raise GlobalMemoryError(ErrorCode.NOTE_INVALID, "The backup file list does not match its manifest.")
        for name in names:
            destination = (vault / name).resolve()
            if not destination.is_relative_to(vault.resolve()):
                raise GlobalMemoryError(ErrorCode.PATH_OUTSIDE_VAULT, "The backup contains an unsafe path.")
            content = archive.read(name)
            if hashlib.sha256(content).hexdigest() != manifest[name]:
                raise GlobalMemoryError(ErrorCode.NOTE_INVALID, "A backup file failed integrity verification.")
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
    return len(names)
