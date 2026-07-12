from __future__ import annotations

import plistlib
import sys
import zipfile
from pathlib import Path

import pytest

from global_memory.errors import ErrorCode, GlobalMemoryError
from global_memory.operations import (
    MANAGED_MARKER,
    backup_vault,
    disable_service,
    enable_service,
    install_service,
    render_service_file,
    restore_vault,
    uninstall_service,
)


def test_backup_restore_round_trip_and_non_overwrite(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    (vault / "folder").mkdir(parents=True)
    (vault / "folder/note.md").write_text("durable\n")
    archive = backup_vault(vault, tmp_path / "backups/memory.zip")

    restored = tmp_path / "restored"
    assert restore_vault(archive, restored) == 1
    assert (restored / "folder/note.md").read_text() == "durable\n"
    with pytest.raises(GlobalMemoryError) as caught:
        restore_vault(archive, restored)
    assert caught.value.code is ErrorCode.VAULT_NOT_WRITABLE


def test_restore_rejects_zip_traversal(tmp_path: Path) -> None:
    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as stream:
        stream.writestr("../outside.md", "unsafe")
        stream.writestr(
            ".global-memory-backup.json",
            '{"files":{"../outside.md":"' + "0" * 64 + '"}}',
        )
    with pytest.raises(GlobalMemoryError) as caught:
        restore_vault(archive, tmp_path / "vault")
    assert caught.value.code is ErrorCode.PATH_OUTSIDE_VAULT
    assert not (tmp_path / "outside.md").exists()


@pytest.mark.parametrize("kind", ["launchd", "systemd"])
def test_native_service_files_are_valid_idempotent_and_managed(tmp_path: Path, kind: str) -> None:
    service = render_service_file(
        kind,
        config_file=tmp_path / "config.toml",
        home=tmp_path / "home",
        executable="/usr/bin/python3",
    )
    assert MANAGED_MARKER.encode() in service.content
    assert str(tmp_path / "config.toml").encode() in service.content
    if kind == "launchd":
        parsed = plistlib.loads(service.content)
        assert parsed["RunAtLoad"] and parsed["KeepAlive"]
    else:
        assert b"WantedBy=default.target" in service.content

    assert install_service(service) == service.path
    assert install_service(service) == service.path
    assert uninstall_service(service)
    assert not uninstall_service(service)


def test_service_install_refuses_unmanaged_file(tmp_path: Path) -> None:
    service = render_service_file("systemd", config_file=tmp_path / "c", home=tmp_path)
    service.path.parent.mkdir(parents=True)
    service.path.write_text("user service\n")
    with pytest.raises(GlobalMemoryError) as caught:
        install_service(service)
    assert caught.value.code is ErrorCode.INTEGRATION_CONFLICT
    with pytest.raises(GlobalMemoryError) as disable_caught:
        disable_service(service)
    assert disable_caught.value.code is ErrorCode.INTEGRATION_CONFLICT


@pytest.mark.parametrize("kind", ["launchd", "systemd"])
def test_native_service_enable_and_disable_commands(tmp_path: Path, kind: str, monkeypatch: pytest.MonkeyPatch) -> None:
    service = render_service_file(kind, config_file=tmp_path / "config.toml", home=tmp_path)
    install_service(service)
    calls: list[tuple[list[str], bool]] = []

    def record(command: list[str], *, check: bool) -> None:
        calls.append((command, check))

    monkeypatch.setattr("global_memory.operations.subprocess.run", record)
    enabled = enable_service(service)
    disabled = disable_service(service)

    assert enabled and disabled
    if kind == "launchd":
        assert enabled[0][:2] == ["launchctl", "bootout"]
        assert enabled[1][:2] == ["launchctl", "bootstrap"]
        assert calls[0][1] is False and calls[1][1] is True
    else:
        assert enabled[1] == ["systemctl", "--user", "enable", "--now", "global-memory.service"]
        assert disabled[0] == ["systemctl", "--user", "disable", "--now", "global-memory.service"]


def test_package_change_uses_active_interpreter_and_pinned_rollback(monkeypatch: pytest.MonkeyPatch) -> None:
    commands: list[list[str]] = []

    def record(command: list[str], *, check: bool) -> None:
        assert check
        commands.append(command)

    monkeypatch.setattr("global_memory.operations.subprocess.run", record)
    from global_memory.operations import package_change

    package_change()
    package_change("0.0.9")
    assert commands[0][-1] == "global-memory-mcp"
    assert commands[1][-1] == "global-memory-mcp==0.0.9"


def test_package_change_supports_uv_managed_environments_without_pip(monkeypatch: pytest.MonkeyPatch) -> None:
    commands: list[list[str]] = []
    monkeypatch.setattr("global_memory.operations.importlib.util.find_spec", lambda _name: None)
    monkeypatch.setattr("global_memory.operations.shutil.which", lambda _name: "/usr/local/bin/uv")
    monkeypatch.setattr(
        "global_memory.operations.subprocess.run",
        lambda command, *, check: commands.append(command),
    )
    from global_memory.operations import package_change

    package_change("0.0.8")

    assert commands == [
        [
            "/usr/local/bin/uv",
            "pip",
            "install",
            "--python",
            sys.executable,
            "--upgrade",
            "global-memory-mcp==0.0.8",
        ]
    ]
