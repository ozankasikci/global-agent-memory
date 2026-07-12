from __future__ import annotations

from pathlib import Path

import pytest

from global_memory.application.diagnostics_service import run_diagnostics
from global_memory.config import EmbeddingSettings, GlobalMemorySettings, PlatformPaths
from global_memory.index.database import IndexDatabase
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


async def test_doctor_inspects_healthy_generated_state_and_reports_invalid_memory(tmp_path: Path) -> None:
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
    database = IndexDatabase(paths.database)
    database.connection.execute(
        "INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "mem_deleted_fixture",
            "deleted.md",
            "Deleted verifier fixture",
            "fact",
            "project",
            "deactivated-verifier-project",
            "active",
            0.5,
            0.5,
            "2026-07-11T00:00:00+00:00",
            "2026-07-11T00:00:00+00:00",
            "deleted",
            "{}",
            "2026-07-11T00:00:00+00:00",
            "2026-07-11T00:00:01+00:00",
            "standard",
        ),
    )
    database.close()
    invalid = settings.vault_path / "10 Global/Reusable Knowledge/invalid.md"
    invalid.write_text("# missing managed frontmatter\n")

    report = await run_diagnostics(settings, paths)
    checks = {check.name: check for check in report.checks}

    assert not report.ok
    assert checks["sqlite"].status == "pass"
    assert checks["stale_jobs"].status == "pass"
    assert checks["unresolved_projects"].status == "pass"
    assert checks["invalid_frontmatter"].status == "fail"
