"""Vault backup and restore operations."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import tempfile
import uuid
import zipfile
from pathlib import Path, PurePosixPath

from global_memory.errors import ErrorCode, GlobalMemoryError

_MANIFEST_NAME = ".global-memory-backup.json"
_MAX_FILES = 100_000
_MAX_UNCOMPRESSED_BYTES = 2_000_000_000


def _unsafe_archive_path(name: str) -> bool:
    path = PurePosixPath(name)
    return not name or path.is_absolute() or ".." in path.parts


def backup_vault(vault: Path, destination: Path) -> Path:
    """Create a self-describing archive of the canonical Vault only."""
    if not vault.is_dir():
        raise GlobalMemoryError(ErrorCode.VAULT_NOT_FOUND, "The configured Vault does not exist.")
    vault = vault.resolve()
    destination = destination.resolve()
    if destination.is_relative_to(vault):
        raise GlobalMemoryError(
            ErrorCode.PATH_OUTSIDE_VAULT,
            "Backups must be written outside the canonical Vault.",
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, str] = {}
    temporary = destination.parent / f".{destination.name}.{uuid.uuid4().hex}.tmp"
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(vault.rglob("*")):
                if path.is_symlink():
                    raise GlobalMemoryError(
                        ErrorCode.PATH_OUTSIDE_VAULT,
                        "The Vault contains a symbolic link, which cannot be included safely.",
                        details={"path": path.relative_to(vault).as_posix()},
                    )
                if not path.is_file():
                    continue
                resolved = path.resolve()
                if not resolved.is_relative_to(vault):
                    raise GlobalMemoryError(ErrorCode.PATH_OUTSIDE_VAULT, "A Vault file resolves outside the Vault.")
                relative = path.relative_to(vault).as_posix()
                content = path.read_bytes()
                archive.writestr(relative, content)
                manifest[relative] = hashlib.sha256(content).hexdigest()
            archive.writestr(_MANIFEST_NAME, json.dumps({"files": manifest}, sort_keys=True))
        with temporary.open("rb") as stream:
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def restore_vault(archive_path: Path, vault: Path) -> int:
    """Verify a backup in staging, then atomically install it into an empty destination."""
    if vault.exists() and any(vault.iterdir()):
        raise GlobalMemoryError(
            ErrorCode.VAULT_NOT_WRITABLE,
            "Restore requires an empty destination so existing notes cannot be overwritten.",
            remediation="Move the existing Vault aside or restore to a new absolute path.",
        )
    vault.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".global-memory-restore-", dir=vault.parent))
    try:
        with zipfile.ZipFile(archive_path) as archive:
            try:
                manifest = json.loads(archive.read(_MANIFEST_NAME))["files"]
            except (KeyError, TypeError, json.JSONDecodeError) as exc:
                raise GlobalMemoryError(ErrorCode.NOTE_INVALID, "The backup manifest is missing or invalid.") from exc
            infos = [info for info in archive.infolist() if info.filename != _MANIFEST_NAME]
            names = [info.filename for info in infos]
            if len(names) != len(set(names)):
                raise GlobalMemoryError(ErrorCode.NOTE_INVALID, "The backup contains duplicate file names.")
            if not isinstance(manifest, dict) or set(names) != set(manifest):
                raise GlobalMemoryError(ErrorCode.NOTE_INVALID, "The backup file list does not match its manifest.")
            if len(infos) > _MAX_FILES or sum(info.file_size for info in infos) > _MAX_UNCOMPRESSED_BYTES:
                raise GlobalMemoryError(ErrorCode.NOTE_INVALID, "The backup exceeds the safe restore limit.")
            for info in infos:
                mode = info.external_attr >> 16
                if (
                    info.is_dir()
                    or _unsafe_archive_path(info.filename)
                    or stat.S_ISLNK(mode)
                    or not isinstance(manifest[info.filename], str)
                ):
                    raise GlobalMemoryError(ErrorCode.PATH_OUTSIDE_VAULT, "The backup contains an unsafe path.")
                content = archive.read(info)
                if hashlib.sha256(content).hexdigest() != manifest[info.filename]:
                    raise GlobalMemoryError(ErrorCode.NOTE_INVALID, "A backup file failed integrity verification.")
                destination = staging.joinpath(*PurePosixPath(info.filename).parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(content)
        if vault.exists():
            vault.rmdir()
        os.replace(staging, vault)
        return len(infos)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
