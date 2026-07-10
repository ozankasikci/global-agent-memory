from __future__ import annotations

import json
from pathlib import Path

import pytest

from global_memory.errors import ErrorCode, GlobalMemoryError
from global_memory.integrations.manager import ClientSpec, IntegrationManager

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
    assert first == second
    assert len(adapter.register_calls) == 1
    assert "unrelated instructions" in instruction.read_text()
    assert instruction.read_text().count("BEGIN GLOBAL MEMORY MCP") == 1
    manifest = json.loads(manager.manifest_path.read_text())
    assert manifest["clients"][client]["skill_hash"] == first.skill_hash
    assert manifest["clients"][client]["config_backup"]
    assert manifest["clients"][client]["instruction_backup"]
    assert manager.status(client)["skill_valid"]  # type: ignore[arg-type]

    assert manager.uninstall(client)  # type: ignore[arg-type]
    assert not skill.exists()
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
