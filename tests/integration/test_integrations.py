from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from global_memory.errors import ErrorCode, GlobalMemoryError
from global_memory.integrations.manager import (
    COMMAND_SKILLS,
    SPECS,
    ClientSpec,
    CLIRegistrationAdapter,
    IntegrationManager,
)

pytestmark = pytest.mark.integration


class FakeAdapter:
    def __init__(self, available: bool = True) -> None:
        self.is_available = available
        self.registered: set[str] = set()
        self.register_calls: list[list[str]] = []
        self.unregister_calls: list[str] = []

    def available(self, spec: ClientSpec) -> bool:
        return self.is_available

    def is_registered(self, spec: ClientSpec, command: list[str]) -> bool:
        del command
        return spec.name in self.registered

    def register(self, spec: ClientSpec, command: list[str]) -> None:
        self.registered.add(spec.name)
        self.register_calls.append(command)

    def unregister(self, spec: ClientSpec) -> None:
        self.registered.remove(spec.name)
        self.unregister_calls.append(spec.name)


class FailingAdapter(FakeAdapter):
    def register(self, spec: ClientSpec, command: list[str]) -> None:
        super().register(spec, command)
        raise GlobalMemoryError(ErrorCode.INTEGRATION_VERIFY_FAILED, "injected registration failure")


def test_cli_registration_requires_a_healthy_executable(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = CLIRegistrationAdapter()
    spec = SPECS["codex"]
    monkeypatch.setattr("global_memory.integrations.manager.shutil.which", lambda _name: None)
    assert not adapter.available(spec)

    monkeypatch.setattr("global_memory.integrations.manager.shutil.which", lambda _name: "/usr/bin/codex")
    monkeypatch.setattr(
        "global_memory.integrations.manager.subprocess.run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess([], 0),
    )
    assert adapter.available(spec)

    monkeypatch.setattr(
        "global_memory.integrations.manager.subprocess.run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess([], 1),
    )
    assert not adapter.available(spec)


@pytest.mark.parametrize("failure", [OSError("missing binary"), subprocess.TimeoutExpired("codex", 10)])
def test_cli_registration_treats_version_probe_failures_as_unavailable(
    monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    monkeypatch.setattr("global_memory.integrations.manager.shutil.which", lambda _name: "/usr/bin/codex")

    def fail(*_args: object, **_kwargs: object) -> None:
        raise failure

    monkeypatch.setattr("global_memory.integrations.manager.subprocess.run", fail)
    assert not CLIRegistrationAdapter().available(SPECS["codex"])


@pytest.mark.parametrize("client", ["claude-code", "codex"])
def test_fake_home_install_is_idempotent_manifested_and_safely_uninstalled(tmp_path: Path, client: str) -> None:
    home = tmp_path / "home"
    home.mkdir()
    adapter = FakeAdapter()
    manager = IntegrationManager(
        home,
        tmp_path / "state",
        adapter=adapter,
        proxy_executable="/bin/global-memory-mcp",
        token_file=tmp_path / "token",
    )
    instruction = home / (".claude/CLAUDE.md" if client == "claude-code" else ".codex/AGENTS.md")
    instruction.parent.mkdir(parents=True)
    instruction.write_text("unrelated instructions\n")
    config = home / (".claude.json" if client == "claude-code" else ".codex/config.toml")
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text('{"theme":"dark"}\n' if client == "claude-code" else 'model = "gpt"\n')

    first = manager.install(client, copy=client == "codex", with_global_instructions=True)  # type: ignore[arg-type]
    second = manager.install(client, copy=client == "codex", with_global_instructions=True)  # type: ignore[arg-type]

    skill = Path(first.skill_path)
    assert skill.is_dir() and (skill.is_symlink() if client == "claude-code" else not skill.is_symlink())
    command_paths = [Path(path) for path in first.command_paths]
    assert [path.name for path in command_paths] == list(COMMAND_SKILLS)
    assert all(path.is_dir() for path in command_paths)
    assert all(path.is_symlink() for path in command_paths) is (client == "claude-code")
    assert first == second
    assert len(adapter.register_calls) == 1
    assert "unrelated instructions" in instruction.read_text()
    assert instruction.read_text().count("BEGIN GLOBAL MEMORY MCP") == 1
    manifest = json.loads(manager.manifest_path.read_text())
    assert manifest["clients"][client]["skill_hash"] == first.skill_hash
    assert manifest["clients"][client]["config_backup"]
    assert manifest["clients"][client]["instruction_backup"]
    assert manager.status(client)["skill_valid"]  # type: ignore[arg-type]
    assert manager.status(client)["commands_valid"]  # type: ignore[arg-type]

    assert manager.uninstall(client)  # type: ignore[arg-type]
    assert not skill.exists()
    assert not any(path.exists() for path in command_paths)
    assert instruction.read_text() == "unrelated instructions\n"
    assert config.read_text() == ('{"theme":"dark"}\n' if client == "claude-code" else 'model = "gpt"\n')
    assert adapter.unregister_calls == [client]
    assert not manager.uninstall(client)  # type: ignore[arg-type]


def test_unmanaged_conflicts_and_modified_managed_artifacts_are_never_silently_replaced(tmp_path: Path) -> None:
    home = tmp_path / "home"
    target = home / ".agents/skills/global-memory"
    target.mkdir(parents=True)
    (target / "user.txt").write_text("mine")
    manager = IntegrationManager(home, tmp_path / "state", adapter=FakeAdapter())
    with pytest.raises(GlobalMemoryError) as unmanaged:
        manager.install("codex", force=True)
    assert unmanaged.value.code is ErrorCode.INTEGRATION_CONFLICT

    target.rename(home / "unmanaged-backup")
    installed = manager.install("codex", copy=True)
    (Path(installed.skill_path) / "SKILL.md").write_text("modified")
    with pytest.raises(GlobalMemoryError):
        manager.install("codex", copy=True)
    manager.install("codex", copy=True, force=True)
    assert "modified" not in (Path(installed.skill_path) / "SKILL.md").read_text()


def test_guarded_config_fallback_preserves_unrelated_json_and_toml(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    adapter = FakeAdapter(available=False)
    manager = IntegrationManager(home, tmp_path / "state", adapter=adapter, proxy_executable="gm-proxy")
    claude = home / ".claude.json"
    claude.write_text('{"theme":"dark"}\n')
    codex = home / ".codex/config.toml"
    codex.parent.mkdir(parents=True)
    codex.write_text('model = "gpt"\n')

    manager.install("claude-code", copy=True)
    manager.install("codex", copy=True)
    assert json.loads(claude.read_text())["theme"] == "dark"
    assert "global-memory" in json.loads(claude.read_text())["mcpServers"]
    assert codex.read_text().startswith('model = "gpt"\n')
    assert "[mcp_servers.global-memory]" in codex.read_text()

    manager.uninstall("claude-code")
    manager.uninstall("codex")
    assert json.loads(claude.read_text()) == {"mcpServers": {}, "theme": "dark"}
    assert codex.read_text() == 'model = "gpt"\n'


def test_dry_run_changes_nothing(tmp_path: Path) -> None:
    home = tmp_path / "home"
    manager = IntegrationManager(home, tmp_path / "state", adapter=FakeAdapter())
    preview = manager.install("codex", dry_run=True, with_global_instructions=True)
    assert preview.name == "codex"
    assert not home.exists()
    assert not manager.manifest_path.exists()


def test_existing_unmanaged_registration_is_not_adopted(tmp_path: Path) -> None:
    adapter = FakeAdapter()
    adapter.registered.add("codex")
    manager = IntegrationManager(tmp_path / "home", tmp_path / "state", adapter=adapter)
    with pytest.raises(GlobalMemoryError) as caught:
        manager.install("codex", copy=True)
    assert caught.value.code is ErrorCode.INTEGRATION_CONFLICT
    assert not manager.manifest_path.exists()


@pytest.mark.parametrize("client", ["claude-code", "codex"])
def test_failed_registration_rolls_back_every_installer_artifact(tmp_path: Path, client: str) -> None:
    home = tmp_path / "home"
    instruction = home / (".claude/CLAUDE.md" if client == "claude-code" else ".codex/AGENTS.md")
    config = home / (".claude.json" if client == "claude-code" else ".codex/config.toml")
    instruction.parent.mkdir(parents=True, exist_ok=True)
    config.parent.mkdir(parents=True, exist_ok=True)
    instruction.write_text("original instructions\n")
    config.write_text('{"theme":"dark"}\n' if client == "claude-code" else 'model = "gpt"\n')
    adapter = FailingAdapter()
    manager = IntegrationManager(home, tmp_path / "state", adapter=adapter)

    with pytest.raises(GlobalMemoryError) as caught:
        manager.install(client, copy=True, with_global_instructions=True)  # type: ignore[arg-type]

    target = home / (".claude/skills/global-memory" if client == "claude-code" else ".agents/skills/global-memory")
    assert caught.value.code is ErrorCode.INTEGRATION_VERIFY_FAILED
    assert not target.exists()
    command_root = target.parent
    assert not any((command_root / name).exists() for name in COMMAND_SKILLS)
    assert instruction.read_text() == "original instructions\n"
    assert config.read_text() == ('{"theme":"dark"}\n' if client == "claude-code" else 'model = "gpt"\n')
    assert client not in adapter.registered
    assert adapter.unregister_calls == [client]
    assert not manager.manifest_path.exists()
    assert not list((tmp_path / "state").glob("backups/**/*.*"))
