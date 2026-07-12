from __future__ import annotations

import os
from pathlib import Path

import pytest

from global_memory.config import GlobalMemorySettings, PlatformPaths, load_settings
from global_memory.errors import ErrorCode, GlobalMemoryError
from global_memory.vault.initialize import MANAGED_DIRECTORIES, initialize


def paths(tmp_path: Path) -> PlatformPaths:
    return PlatformPaths(
        config_dir=tmp_path / "config",
        data_dir=tmp_path / "data",
        log_dir=tmp_path / "data" / "logs",
        runtime_dir=tmp_path / "data" / "run",
    )


def test_config_precedence_cli_over_environment_over_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(f'vault_path = "{tmp_path / "vault"}"\n[mcp]\nport = 8001\n[index]\ndebounce_ms = 700\n')
    monkeypatch.setenv("GLOBAL_MEMORY_MCP__PORT", "8002")

    settings = load_settings(config_file, {"mcp": {"port": 8003}})

    assert settings.mcp.port == 8003
    assert settings.index.debounce_ms == 700


def test_invalid_configuration_reports_all_fields(tmp_path: Path) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text('vault_path = "relative"\n[mcp]\nhost = "0.0.0.0"\nport = 70000\n')

    with pytest.raises(GlobalMemoryError) as caught:
        load_settings(config_file)

    assert caught.value.code is ErrorCode.CONFIG_INVALID
    invalid_fields = {item["field"] for item in caught.value.details["errors"]}
    assert {"vault_path", "mcp.host", "mcp.port"} <= invalid_fields


def test_initialization_is_idempotent_and_protects_token(tmp_path: Path) -> None:
    platform_paths = paths(tmp_path)
    vault = tmp_path / "Global Agent Memory"
    settings = GlobalMemorySettings(vault_path=vault)

    first = initialize(settings, platform_paths)
    token_before = platform_paths.auth_token.read_text()
    second = initialize(settings, platform_paths)

    assert first.created
    assert not second.created
    assert platform_paths.auth_token.read_text() == token_before
    assert os.stat(platform_paths.auth_token).st_mode & 0o777 == 0o600
    assert all((vault / directory).is_dir() for directory in MANAGED_DIRECTORIES)
    assert platform_paths.database.parent == platform_paths.data_dir
    assert not platform_paths.database.is_relative_to(vault)


def test_initialization_never_overwrites_existing_vault_readme(tmp_path: Path) -> None:
    platform_paths = paths(tmp_path)
    vault = tmp_path / "Global Agent Memory"
    vault.mkdir()
    readme = vault / "README.md"
    readme.write_text("user content\n")

    initialize(GlobalMemorySettings(vault_path=vault), platform_paths)

    assert readme.read_text() == "user content\n"


@pytest.mark.parametrize("bad_vault", ["relative", "existing-file"])
def test_initialization_rejects_invalid_vault_paths(tmp_path: Path, bad_vault: str) -> None:
    candidate = Path(bad_vault) if bad_vault == "relative" else tmp_path / bad_vault
    if candidate.is_absolute():
        candidate.write_text("not a directory")

    with pytest.raises(GlobalMemoryError) as caught:
        settings = GlobalMemorySettings(vault_path=candidate)
        initialize(settings, paths(tmp_path))

    assert caught.value.code in {ErrorCode.CONFIG_INVALID, ErrorCode.VAULT_NOT_WRITABLE}
