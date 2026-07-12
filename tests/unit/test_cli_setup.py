from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from typer.testing import CliRunner

import global_memory.cli as cli
from global_memory.config import PlatformPaths
from global_memory.integrations.manager import ClientName
from global_memory.vault.initialize import InitializationResult


def _paths(tmp_path: Path) -> PlatformPaths:
    return PlatformPaths(
        config_dir=tmp_path / "config",
        data_dir=tmp_path / "data",
        log_dir=tmp_path / "logs",
        runtime_dir=tmp_path / "run",
    )


def _patch_home(monkeypatch: pytest.MonkeyPatch, home: Path) -> None:
    monkeypatch.setattr(Path, "home", classmethod(lambda _class: home))


@dataclass
class FakeManager:
    home: Path
    state_dir: Path
    endpoint: str = "http://127.0.0.1:8765/mcp/"
    token_file: Path | None = None

    installed: list[ClientName] | None = None
    install_options: list[dict[str, Any]] | None = None
    available: bool = True

    def __post_init__(self) -> None:
        self.installed = []
        self.install_options = []

    def install(self, client: ClientName, **options: Any) -> SimpleNamespace:
        assert self.installed is not None and self.install_options is not None
        self.installed.append(client)
        self.install_options.append(options)
        return SimpleNamespace(skill_path=self.home / ".skills" / client)

    def status(self, client: ClientName) -> dict[str, Any]:
        assert self.installed is not None
        managed = client in self.installed
        return {
            "managed": managed,
            "client_available": self.available,
            "skill_valid": managed,
            "commands_valid": managed,
            "mcp_registered": managed,
        }


def test_setup_dry_run_uses_safe_defaults_without_writing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = _paths(tmp_path)
    home = tmp_path / "home"
    _patch_home(monkeypatch, home)
    monkeypatch.setattr(cli, "get_platform_paths", lambda: paths)

    result = CliRunner().invoke(
        cli.app,
        ["setup", "--clients", "none", "--no-service", "--no-open-dashboard", "--dry-run"],
    )

    assert result.exit_code == 0, result.output
    assert f"Vault: {home / 'Documents/Global Agent Memory'}" in result.output
    assert "Agent integrations: none detected" in result.output
    assert "No changes were made" in result.output
    assert not paths.config_dir.exists()
    assert not (home / "Documents/Global Agent Memory").exists()


def test_setup_composes_initialization_daemon_and_requested_clients(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _paths(tmp_path)
    home = tmp_path / "home"
    vault = tmp_path / "vault"
    _patch_home(monkeypatch, home)
    monkeypatch.setattr(cli, "get_platform_paths", lambda: paths)
    managers: list[FakeManager] = []

    def manager(*args: Any, **kwargs: Any) -> FakeManager:
        value = FakeManager(*args, **kwargs)
        managers.append(value)
        return value

    initialized: list[Path] = []

    def initialize(settings: Any, _paths_value: PlatformPaths) -> InitializationResult:
        initialized.append(settings.vault_path)
        return InitializationResult(settings.vault_path, paths.config_file, True)

    monkeypatch.setattr(cli, "IntegrationManager", manager)
    monkeypatch.setattr(cli, "initialize", initialize)
    monkeypatch.setattr(
        cli,
        "start_daemon",
        lambda _settings, _paths_value: SimpleNamespace(endpoint="http://127.0.0.1:8765/mcp/"),
    )

    result = CliRunner().invoke(
        cli.app,
        [
            "setup",
            "--vault",
            str(vault),
            "--clients",
            "all",
            "--no-service",
            "--no-verify",
            "--no-open-dashboard",
            "--yes",
        ],
    )

    assert result.exit_code == 0, result.output
    assert initialized == [vault]
    assert managers[0].installed == ["claude-code", "codex"]
    assert all(options["force"] is True for options in managers[0].install_options or [])
    assert "Setup complete" in result.output


def test_setup_auto_detects_a_broken_client_and_uses_guarded_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _paths(tmp_path)
    home = tmp_path / "home"
    _patch_home(monkeypatch, home)
    monkeypatch.setattr(cli, "get_platform_paths", lambda: paths)
    manager = FakeManager(home, paths.data_dir, available=False)
    monkeypatch.setattr(cli, "IntegrationManager", lambda *_args, **_kwargs: manager)
    monkeypatch.setattr(shutil, "which", lambda executable: "/usr/bin/codex" if executable == "codex" else None)
    monkeypatch.setattr(
        cli,
        "initialize",
        lambda settings, _paths_value: InitializationResult(settings.vault_path, paths.config_file, True),
    )
    monkeypatch.setattr(
        cli,
        "start_daemon",
        lambda _settings, _paths_value: SimpleNamespace(endpoint="http://127.0.0.1:8765/mcp/"),
    )

    result = CliRunner().invoke(
        cli.app,
        ["setup", "--no-service", "--no-open-dashboard", "--yes"],
    )

    assert result.exit_code == 0, result.output
    assert manager.installed == ["codex"]
    assert "codex configured, but its executable could not be run" in result.output
    assert "Setup complete" in result.output


def test_setup_installs_and_waits_for_native_service(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = _paths(tmp_path)
    home = tmp_path / "home"
    _patch_home(monkeypatch, home)
    monkeypatch.setattr(cli, "get_platform_paths", lambda: paths)
    monkeypatch.setattr(cli, "_setup_service_kind", lambda: "launchd")
    monkeypatch.setattr(
        cli,
        "initialize",
        lambda settings, _paths_value: InitializationResult(settings.vault_path, paths.config_file, True),
    )
    service = SimpleNamespace(kind="launchd", path=home / "service")
    calls: list[str] = []
    monkeypatch.setattr(cli, "render_service_file", lambda *_args, **_kwargs: service)
    monkeypatch.setattr(cli, "install_service", lambda _service: calls.append("install"))
    monkeypatch.setattr(cli, "enable_service", lambda _service: calls.append("enable"))
    monkeypatch.setattr(cli, "_wait_for_setup_daemon", lambda _endpoint: calls.append("wait"))

    result = CliRunner().invoke(
        cli.app,
        ["setup", "--clients", "none", "--no-verify", "--no-open-dashboard", "--yes"],
    )

    assert result.exit_code == 0, result.output
    assert calls == ["install", "enable", "wait"]
    assert "launchd service installed and ready" in result.output


def test_setup_refuses_to_silently_replace_an_existing_vault_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _paths(tmp_path)
    home = tmp_path / "home"
    _patch_home(monkeypatch, home)
    paths.config_dir.mkdir(parents=True)
    paths.config_file.write_text(f'vault_path = "{tmp_path / "existing"}"\n')
    monkeypatch.setattr(cli, "get_platform_paths", lambda: paths)

    result = CliRunner().invoke(
        cli.app,
        ["setup", "--vault", str(tmp_path / "different"), "--clients", "none", "--dry-run"],
    )

    assert result.exit_code == 2
    assert "Setup cannot replace the Vault path" in result.output
