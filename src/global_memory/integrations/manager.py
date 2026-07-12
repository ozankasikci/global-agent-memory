"""Shared safe installer for Claude Code and Codex."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol

from global_memory.errors import ErrorCode, GlobalMemoryError

ClientName = Literal["claude-code", "codex"]
SERVER_NAME = "global-memory"
COMMAND_SKILLS = ("gam-context", "gam-search", "gam-remember", "gam-review", "gam-dashboard")


@dataclass(frozen=True, slots=True)
class ClientSpec:
    name: ClientName
    executable: str
    skill_relative: Path
    instructions_relative: Path
    config_relative: Path
    snippet_relative: Path


SPECS: dict[ClientName, ClientSpec] = {
    "claude-code": ClientSpec(
        "claude-code",
        "claude",
        Path(".claude/skills/global-memory"),
        Path(".claude/CLAUDE.md"),
        Path(".claude.json"),
        Path("claude-code/CLAUDE.md.snippet"),
    ),
    "codex": ClientSpec(
        "codex",
        "codex",
        Path(".agents/skills/global-memory"),
        Path(".codex/AGENTS.md"),
        Path(".codex/config.toml"),
        Path("codex/AGENTS.md.snippet"),
    ),
}


class RegistrationAdapter(Protocol):
    def available(self, spec: ClientSpec) -> bool: ...
    def is_registered(self, spec: ClientSpec, command: list[str]) -> bool: ...
    def register(self, spec: ClientSpec, command: list[str]) -> None: ...
    def unregister(self, spec: ClientSpec) -> None: ...


class CLIRegistrationAdapter:
    """Preferred official client-CLI registration adapter."""

    def available(self, spec: ClientSpec) -> bool:
        executable = shutil.which(spec.executable)
        if executable is None:
            return False
        try:
            result = subprocess.run([executable, "--version"], capture_output=True, text=True, check=False, timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            return False
        return result.returncode == 0

    def is_registered(self, spec: ClientSpec, command: list[str]) -> bool:
        del command
        result = subprocess.run(
            [spec.executable, "mcp", "get", SERVER_NAME], capture_output=True, text=True, check=False
        )
        return result.returncode == 0

    def register(self, spec: ClientSpec, command: list[str]) -> None:
        arguments = [spec.executable, "mcp", "add", SERVER_NAME]
        if spec.name == "claude-code":
            arguments.extend(["--scope", "user"])
        arguments.extend(["--", *command])
        self._run(arguments)

    def unregister(self, spec: ClientSpec) -> None:
        arguments = [spec.executable, "mcp", "remove", SERVER_NAME]
        if spec.name == "claude-code":
            arguments.extend(["--scope", "user"])
        self._run(arguments)

    @staticmethod
    def _run(arguments: list[str]) -> None:
        try:
            subprocess.run(arguments, check=True)
        except (OSError, subprocess.CalledProcessError) as exc:
            raise GlobalMemoryError(
                ErrorCode.INTEGRATION_VERIFY_FAILED,
                "The client MCP registration command failed.",
                details={"executable": arguments[0], "operation": arguments[1:3]},
            ) from exc


@dataclass(frozen=True, slots=True)
class InstalledClient:
    name: ClientName
    skill_path: str
    skill_mode: str
    skill_hash: str
    instruction_path: str | None
    instruction_hash: str | None
    instruction_backup: str | None
    config_path: str
    config_backup: str | None
    registration_mode: str
    command: list[str]
    command_paths: list[str]
    command_hashes: dict[str, str]


def integration_root() -> Path:
    repository = Path(__file__).resolve().parents[3] / "integrations"
    return repository if repository.is_dir() else Path(__file__).resolve().parents[1] / "_integration"


def _tree_hash(path: Path) -> str:
    digest = hashlib.sha256()
    for item in sorted(candidate for candidate in path.rglob("*") if candidate.is_file()):
        digest.update(item.relative_to(path).as_posix().encode())
        digest.update(item.read_bytes())
    return digest.hexdigest()


class IntegrationManager:
    def __init__(
        self,
        home: Path,
        state_dir: Path,
        *,
        adapter: RegistrationAdapter | None = None,
        proxy_executable: str = "global-memory-mcp",
        endpoint: str = "http://127.0.0.1:8765/mcp/",
        token_file: Path | None = None,
    ) -> None:
        self.home = home
        self.state_dir = state_dir
        self.adapter = adapter or CLIRegistrationAdapter()
        self.proxy_executable = proxy_executable
        self.endpoint = endpoint
        self.token_file = token_file or home / ".config/global-memory/auth-token"
        self.manifest_path = state_dir / "integrations.json"

    def _manifest(self) -> dict[str, Any]:
        try:
            value = json.loads(self.manifest_path.read_text())
            return value if isinstance(value, dict) else {"version": 1, "clients": {}}
        except (OSError, json.JSONDecodeError):
            return {"version": 1, "clients": {}}

    def _save(self, manifest: dict[str, Any]) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        contents = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        descriptor, temporary_name = tempfile.mkstemp(prefix="integrations.", dir=self.state_dir)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w") as handle:
                handle.write(contents)
            temporary.chmod(0o600)
            temporary.replace(self.manifest_path)
        finally:
            temporary.unlink(missing_ok=True)

    def _command(self) -> list[str]:
        return [
            self.proxy_executable,
            "--endpoint",
            self.endpoint,
            "--token-file",
            str(self.token_file),
        ]

    def _backup(self, path: Path, client: ClientName) -> str | None:
        if not path.exists():
            return None
        backup_dir = self.state_dir / "backups" / client
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        backup = backup_dir / f"{path.name}.{stamp}.bak"
        shutil.copy2(path, backup)
        return str(backup)

    def install(
        self,
        client: ClientName,
        *,
        copy: bool = False,
        with_global_instructions: bool = False,
        dry_run: bool = False,
        force: bool = False,
    ) -> InstalledClient:
        spec = SPECS[client]
        source = integration_root() / "skills/global-memory"
        target = self.home / spec.skill_relative
        command_sources = {name: integration_root() / "skills" / name for name in COMMAND_SKILLS}
        command_targets = {name: target.parent / name for name in COMMAND_SKILLS}
        manifest = self._manifest()
        previous = manifest["clients"].get(client)
        source_hash = _tree_hash(source)
        command_hashes = {name: _tree_hash(path) for name, path in command_sources.items()}
        unmanaged_targets = [
            path for path in (target, *command_targets.values()) if os.path.lexists(path) and previous is None
        ]
        if unmanaged_targets:
            raise GlobalMemoryError(
                ErrorCode.INTEGRATION_CONFLICT,
                "An unmanaged skill target already exists.",
                details={"path": str(unmanaged_targets[0])},
                remediation="Move it aside; --force never replaces unmanaged artifacts.",
            )
        if force and previous is None:
            raise GlobalMemoryError(ErrorCode.INTEGRATION_CONFLICT, "--force applies only to managed artifacts.")
        command = self._command()
        config_path = self.home / spec.config_relative
        backup = previous.get("config_backup") if previous else None
        registration_mode = "cli" if self.adapter.available(spec) else "config"
        instruction_path: str | None = None
        instruction_hash: str | None = None
        instruction_backup = previous.get("instruction_backup") if previous else None
        desired_mode = "copy" if copy else "symlink"
        registered = (
            self.adapter.is_registered(spec, command)
            if registration_mode == "cli"
            else self._fallback_status(spec, config_path, command)
        )
        if registered and previous is None:
            raise GlobalMemoryError(
                ErrorCode.INTEGRATION_CONFLICT,
                "An unmanaged MCP registration already uses the global-memory name.",
                remediation="Remove or rename it explicitly before installing this integration.",
            )
        if not dry_run:
            instructions = self.home / spec.instructions_relative
            manifest_snapshot = self.manifest_path.read_bytes() if self.manifest_path.exists() else None
            config_snapshot = config_path.read_bytes() if config_path.exists() else None
            instruction_snapshot = instructions.read_bytes() if instructions.exists() else None
            created_backups: list[Path] = []
            with tempfile.TemporaryDirectory(prefix="global-memory-integration-") as temporary:
                managed_targets = {"global-memory": target, **command_targets}
                expected_hashes = {"global-memory": source_hash, **command_hashes}
                sources = {"global-memory": source, **command_sources}
                snapshots = {
                    name: (Path(temporary) / name, self._snapshot_path(path, Path(temporary) / name))
                    for name, path in managed_targets.items()
                }
                try:
                    replace_mode = bool(previous) and previous.get("skill_mode") != desired_mode
                    previous_command_hashes = previous.get("command_hashes", {}) if previous else {}
                    for name, managed_target in managed_targets.items():
                        expected = expected_hashes[name]
                        recorded = (
                            previous.get("skill_hash")
                            if previous and name == "global-memory"
                            else previous_command_hashes.get(name)
                        )
                        if os.path.lexists(managed_target) and previous and recorded is None:
                            raise GlobalMemoryError(
                                ErrorCode.INTEGRATION_CONFLICT,
                                "An unmanaged command skill target already exists.",
                                details={"path": str(managed_target)},
                                remediation="Move it aside; managed upgrades never adopt unrelated artifacts.",
                            )
                        if (
                            os.path.lexists(managed_target)
                            and previous
                            and recorded is not None
                            and not self._skill_matches(managed_target, recorded)
                            and not force
                        ):
                            raise GlobalMemoryError(
                                ErrorCode.INTEGRATION_CONFLICT,
                                "A managed skill differs from the installed version.",
                                details={"path": str(managed_target)},
                                remediation=(
                                    "Inspect the changes, then use --force only to replace this managed artifact."
                                ),
                            )
                        if os.path.lexists(managed_target) and (
                            force or replace_mode or not self._skill_matches(managed_target, expected)
                        ):
                            self._remove_path(managed_target)
                        if not os.path.lexists(managed_target):
                            managed_target.parent.mkdir(parents=True, exist_ok=True)
                            if copy:
                                shutil.copytree(sources[name], managed_target)
                            else:
                                managed_target.symlink_to(sources[name], target_is_directory=True)
                    if with_global_instructions:
                        snippet = (integration_root() / spec.snippet_relative).read_text()
                        if instruction_backup is None:
                            instruction_backup = self._backup(instructions, client)
                            if instruction_backup is not None:
                                created_backups.append(Path(instruction_backup))
                        self._install_snippet(instructions, snippet)
                        instruction_path = str(instructions)
                        instruction_hash = hashlib.sha256(snippet.encode()).hexdigest()
                    elif previous:
                        instruction_path = previous.get("instruction_path")
                        instruction_hash = previous.get("instruction_hash")
                    if not registered:
                        backup = self._backup(config_path, client)
                        if backup is not None:
                            created_backups.append(Path(backup))
                        if registration_mode == "cli":
                            self.adapter.register(spec, command)
                        else:
                            self._fallback_register(spec, config_path, command)
                    installed = InstalledClient(
                        client,
                        str(target),
                        "copy" if copy else "symlink",
                        source_hash,
                        instruction_path,
                        instruction_hash,
                        instruction_backup,
                        str(config_path),
                        backup,
                        registration_mode,
                        command,
                        [str(command_targets[name]) for name in COMMAND_SKILLS],
                        command_hashes,
                    )
                    manifest["clients"][client] = asdict(installed)
                    self._save(manifest)
                    return installed
                except Exception:
                    if not registered and registration_mode == "cli":
                        try:
                            if self.adapter.is_registered(spec, command):
                                self.adapter.unregister(spec)
                        except Exception:
                            pass
                    for name, managed_target in managed_targets.items():
                        snapshot, kind = snapshots[name]
                        self._restore_path(managed_target, snapshot, kind)
                    self._restore_file(instructions, instruction_snapshot)
                    self._restore_file(config_path, config_snapshot)
                    self._restore_file(self.manifest_path, manifest_snapshot, mode=0o600)
                    for created_backup in created_backups:
                        created_backup.unlink(missing_ok=True)
                    raise
        return InstalledClient(
            client,
            str(target),
            "copy" if copy else "symlink",
            source_hash,
            str(self.home / spec.instructions_relative) if with_global_instructions else None,
            None,
            None,
            str(config_path),
            backup,
            registration_mode,
            command,
            [str(command_targets[name]) for name in COMMAND_SKILLS],
            command_hashes,
        )

    @staticmethod
    def _skill_matches(target: Path, expected_hash: str) -> bool:
        try:
            return _tree_hash(target.resolve()) == expected_hash
        except OSError:
            return False

    @staticmethod
    def _remove_path(path: Path) -> None:
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        elif os.path.lexists(path):
            path.unlink()

    @classmethod
    def _snapshot_path(cls, path: Path, snapshot: Path) -> str:
        if not os.path.lexists(path):
            return "missing"
        if path.is_symlink():
            snapshot.write_text(os.readlink(path))
            return "symlink"
        if path.is_dir():
            shutil.copytree(path, snapshot)
            return "directory"
        shutil.copy2(path, snapshot)
        return "file"

    @classmethod
    def _restore_path(cls, path: Path, snapshot: Path, kind: str) -> None:
        cls._remove_path(path)
        if kind == "missing":
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        if kind == "symlink":
            path.symlink_to(snapshot.read_text(), target_is_directory=True)
        elif kind == "directory":
            shutil.copytree(snapshot, path)
        else:
            shutil.copy2(snapshot, path)

    @staticmethod
    def _restore_file(path: Path, contents: bytes | None, *, mode: int | None = None) -> None:
        if contents is None:
            path.unlink(missing_ok=True)
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents)
        if mode is not None:
            path.chmod(mode)

    @staticmethod
    def _install_snippet(path: Path, snippet: str) -> None:
        existing = path.read_text() if path.exists() else ""
        begin, end = snippet.splitlines()[0], snippet.splitlines()[-1]
        if begin in existing:
            start = existing.index(begin)
            finish = existing.index(end, start) + len(end)
            updated = existing[:start] + snippet.rstrip() + existing[finish:]
        else:
            separator = "" if not existing or existing.endswith("\n\n") else "\n"
            updated = existing + separator + snippet.rstrip() + "\n"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(updated)

    def _fallback_register(self, spec: ClientSpec, config: Path, command: list[str]) -> None:
        config.parent.mkdir(parents=True, exist_ok=True)
        if spec.name == "claude-code":
            try:
                value = json.loads(config.read_text()) if config.exists() else {}
            except json.JSONDecodeError as exc:
                raise GlobalMemoryError(ErrorCode.INTEGRATION_CONFLICT, "Claude user config is invalid JSON.") from exc
            servers = value.setdefault("mcpServers", {})
            existing = servers.get(SERVER_NAME)
            desired = {"type": "stdio", "command": command[0], "args": command[1:]}
            if existing not in (None, desired):
                raise GlobalMemoryError(ErrorCode.INTEGRATION_CONFLICT, "An unmanaged MCP registration exists.")
            servers[SERVER_NAME] = desired
            config.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
            return
        begin = "# BEGIN GLOBAL MEMORY MCP"
        end = "# END GLOBAL MEMORY MCP"
        existing = config.read_text() if config.exists() else ""
        if f"[mcp_servers.{SERVER_NAME}]" in existing and begin not in existing:
            raise GlobalMemoryError(ErrorCode.INTEGRATION_CONFLICT, "An unmanaged MCP registration exists.")
        block = (
            f"{begin}\n[mcp_servers.{SERVER_NAME}]\ncommand = {json.dumps(command[0])}\n"
            f"args = {json.dumps(command[1:])}\n{end}"
        )
        if begin in existing:
            start = existing.index(begin)
            finish = existing.index(end, start) + len(end)
            existing = existing[:start] + block + existing[finish:]
        else:
            existing = existing + ("\n" if existing and not existing.endswith("\n") else "") + block + "\n"
        config.write_text(existing)

    def status(self, client: ClientName) -> dict[str, Any]:
        spec = SPECS[client]
        manifest = self._manifest()["clients"].get(client)
        target = self.home / spec.skill_relative
        command_targets = {name: target.parent / name for name in COMMAND_SKILLS}
        command = self._command()
        command_hashes = manifest.get("command_hashes", {}) if manifest else {}
        return {
            "client": client,
            "managed": manifest is not None,
            "client_available": self.adapter.available(spec),
            "skill_installed": os.path.lexists(target),
            "skill_valid": bool(manifest) and self._skill_matches(target, manifest["skill_hash"]),
            "commands_installed": all(os.path.lexists(path) for path in command_targets.values()),
            "commands_valid": bool(manifest)
            and all(
                name in command_hashes and self._skill_matches(path, command_hashes[name])
                for name, path in command_targets.items()
            ),
            "mcp_registered": self.adapter.is_registered(spec, command)
            if self.adapter.available(spec)
            else self._fallback_status(spec, self.home / spec.config_relative, command),
        }

    @staticmethod
    def _fallback_status(spec: ClientSpec, config: Path, command: list[str]) -> bool:
        if not config.exists():
            return False
        text = config.read_text()
        if spec.name == "codex":
            return "# BEGIN GLOBAL MEMORY MCP" in text and f"[mcp_servers.{SERVER_NAME}]" in text
        try:
            server = json.loads(text).get("mcpServers", {}).get(SERVER_NAME)
        except json.JSONDecodeError:
            return False
        return bool(server == {"type": "stdio", "command": command[0], "args": command[1:]})

    def uninstall(self, client: ClientName, *, dry_run: bool = False) -> bool:
        spec = SPECS[client]
        manifest = self._manifest()
        record = manifest["clients"].get(client)
        if record is None:
            return False
        if dry_run:
            return True
        target = Path(record["skill_path"])
        managed_commands = [
            (Path(path_value), record.get("command_hashes", {}).get(Path(path_value).name))
            for path_value in record.get("command_paths", [])
        ]
        if os.path.lexists(target) and not self._skill_matches(target, record["skill_hash"]):
            raise GlobalMemoryError(ErrorCode.INTEGRATION_CONFLICT, "The managed skill was modified.")
        for command_target, expected_hash in managed_commands:
            if os.path.lexists(command_target) and (
                expected_hash is None or not self._skill_matches(command_target, expected_hash)
            ):
                raise GlobalMemoryError(ErrorCode.INTEGRATION_CONFLICT, "A managed command skill was modified.")
        if os.path.lexists(target):
            if target.is_dir() and not target.is_symlink():
                shutil.rmtree(target)
            else:
                target.unlink()
        for command_target, _ in managed_commands:
            if os.path.lexists(command_target):
                self._remove_path(command_target)
        if record.get("instruction_path"):
            self._remove_snippet(Path(record["instruction_path"]), record["instruction_hash"])
        if record["registration_mode"] == "cli" and self.adapter.available(spec):
            if self.adapter.is_registered(spec, record["command"]):
                self.adapter.unregister(spec)
        else:
            self._fallback_unregister(spec, Path(record["config_path"]), record["command"])
        del manifest["clients"][client]
        self._save(manifest)
        return True

    @staticmethod
    def _remove_snippet(path: Path, expected_hash: str) -> None:
        if not path.exists():
            return
        text = path.read_text()
        begin = "<!-- BEGIN GLOBAL MEMORY MCP -->"
        end = "<!-- END GLOBAL MEMORY MCP -->"
        if begin not in text:
            return
        start = text.index(begin)
        finish = text.index(end, start) + len(end)
        block = text[start:finish] + "\n"
        if hashlib.sha256(block.encode()).hexdigest() != expected_hash:
            raise GlobalMemoryError(ErrorCode.INTEGRATION_CONFLICT, "The managed instruction snippet was modified.")
        updated = (text[:start] + text[finish:]).strip("\n")
        path.write_text(updated + ("\n" if updated else ""))

    def _fallback_unregister(self, spec: ClientSpec, config: Path, command: list[str]) -> None:
        if not config.exists():
            return
        text = config.read_text()
        if spec.name == "codex":
            begin, end = "# BEGIN GLOBAL MEMORY MCP", "# END GLOBAL MEMORY MCP"
            if begin in text:
                start = text.index(begin)
                finish = text.index(end, start) + len(end)
                expected = (
                    f"{begin}\n[mcp_servers.{SERVER_NAME}]\ncommand = {json.dumps(command[0])}\n"
                    f"args = {json.dumps(command[1:])}\n{end}"
                )
                if text[start:finish] != expected:
                    raise GlobalMemoryError(
                        ErrorCode.INTEGRATION_CONFLICT, "The managed MCP registration was modified."
                    )
                before, after = text[:start], text[finish:]
                if before.endswith("\n") and after.startswith("\n"):
                    after = after[1:]
                config.write_text(before + after)
            return
        value = json.loads(text)
        expected_registration = {"type": "stdio", "command": command[0], "args": command[1:]}
        if value.get("mcpServers", {}).get(SERVER_NAME) != expected_registration:
            raise GlobalMemoryError(ErrorCode.INTEGRATION_CONFLICT, "The managed MCP registration was modified.")
        del value["mcpServers"][SERVER_NAME]
        config.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
