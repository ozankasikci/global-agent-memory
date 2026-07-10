from __future__ import annotations

from pathlib import Path

import pytest

from global_memory.application.diagnostics_service import run_diagnostics
from global_memory.config import EmbeddingSettings, GlobalMemorySettings, PlatformPaths
from global_memory.vault.initialize import initialize

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_doctor_covers_required_local_subsystems_without_live_daemon(tmp_path: Path) -> None:
    paths = PlatformPaths(
        config_dir=tmp_path / "config",
        data_dir=tmp_path / "data",
        log_dir=tmp_path / "logs",
        runtime_dir=tmp_path / "run",
    )
    settings = GlobalMemorySettings(
        vault_path=tmp_path / "vault",
        embeddings=EmbeddingSettings(enabled=False),
    )
    initialize(settings, paths)

    report = await run_diagnostics(settings, paths)
    names = {check.name for check in report.checks}
    assert report.ok
    assert {
        "configuration",
        "vault",
        "managed_folders",
        "sqlite",
        "vector_adapter",
        "embedding_provider",
        "invalid_frontmatter",
        "duplicate_ids",
        "daemon_readiness",
        "direct_mcp_discovery",
        "stdio_proxy",
        "contract_hashes",
        "claude_code_integration",
        "codex_integration",
    } <= names
