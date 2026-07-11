"""Non-destructive operational diagnostics for `global-memory doctor`."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sqlite3
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

import httpx
import sqlite_vec  # type: ignore[import-untyped]
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamable_http_client

from global_memory.config import GlobalMemorySettings, PlatformPaths
from global_memory.mcp.contract import contract_root, load_discovery
from global_memory.vault.initialize import MANAGED_DIRECTORIES
from global_memory.vault.markdown import parse_note
from global_memory.vault.paths import is_managed_memory_path

type CheckStatus = Literal["pass", "warn", "fail"]


@dataclass(frozen=True, slots=True)
class DiagnosticCheck:
    name: str
    status: CheckStatus
    message: str
    details: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class DiagnosticReport:
    ok: bool
    checks: list[DiagnosticCheck]

    def as_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "checks": [asdict(check) for check in self.checks]}


def _vault_checks(settings: GlobalMemorySettings) -> list[DiagnosticCheck]:
    vault = settings.vault_path
    checks: list[DiagnosticCheck] = []
    writable = vault.is_dir() and os.access(vault, os.W_OK)
    checks.append(DiagnosticCheck("vault", "pass" if writable else "fail", str(vault)))
    missing = [relative for relative in MANAGED_DIRECTORIES if not (vault / relative).is_dir()]
    checks.append(
        DiagnosticCheck(
            "managed_folders",
            "pass" if not missing else "fail",
            "All managed folders exist." if not missing else "Managed folders are missing.",
            {"missing": missing},
        )
    )
    invalid: list[str] = []
    ids: dict[str, list[str]] = {}
    if vault.is_dir():
        for path in vault.rglob("*.md"):
            relative = path.relative_to(vault)
            if not is_managed_memory_path(relative):
                continue
            try:
                parsed = parse_note(path.read_text())
            except Exception:
                invalid.append(relative.as_posix())
            else:
                ids.setdefault(parsed.metadata.id, []).append(relative.as_posix())
    duplicates = {memory_id: paths for memory_id, paths in ids.items() if len(paths) > 1}
    checks.append(
        DiagnosticCheck(
            "invalid_frontmatter", "pass" if not invalid else "fail", f"{len(invalid)} invalid", {"paths": invalid}
        )
    )
    checks.append(
        DiagnosticCheck(
            "duplicate_ids",
            "pass" if not duplicates else "fail",
            f"{len(duplicates)} duplicate IDs",
            {"duplicates": duplicates},
        )
    )
    return checks


def _database_checks(paths: PlatformPaths) -> list[DiagnosticCheck]:
    if not paths.database.exists():
        return [DiagnosticCheck("sqlite", "warn", "Generated database does not exist yet.")]
    checks: list[DiagnosticCheck] = []
    try:
        connection = sqlite3.connect(f"file:{paths.database}?mode=ro", uri=True)
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        journal = connection.execute("PRAGMA journal_mode").fetchone()[0]
        migration = connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
        stale = connection.execute(
            "SELECT COUNT(*) FROM index_jobs WHERE status='pending' AND updated_at < datetime('now','-1 hour')"
        ).fetchone()[0]
        unresolved = connection.execute(
            "SELECT COUNT(DISTINCT d.project) FROM documents d LEFT JOIN projects p "
            "ON p.canonical_name=d.project AND p.active=1 "
            "WHERE d.deleted_at IS NULL AND d.project IS NOT NULL AND p.id IS NULL"
        ).fetchone()[0]
        connection.close()
        checks.append(
            DiagnosticCheck(
                "sqlite",
                "pass" if integrity == "ok" else "fail",
                str(integrity),
                {"migration": migration, "journal": journal},
            )
        )
        checks.append(DiagnosticCheck("stale_jobs", "pass" if not stale else "warn", f"{stale} stale jobs"))
        checks.append(
            DiagnosticCheck(
                "unresolved_projects", "pass" if not unresolved else "warn", f"{unresolved} unresolved projects"
            )
        )
    except sqlite3.DatabaseError as exc:
        checks.append(DiagnosticCheck("sqlite", "fail", "SQLite diagnostics failed.", {"reason": type(exc).__name__}))
    return checks


async def _transport_checks(settings: GlobalMemorySettings, paths: PlatformPaths) -> list[DiagnosticCheck]:
    endpoint = f"http://{settings.mcp.host}:{settings.mcp.port}/mcp/"
    try:
        token = paths.auth_token.read_text().strip()
        async with (
            httpx.AsyncClient(
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"}, timeout=1
            ) as client,
            streamable_http_client(endpoint, http_client=client) as (read_stream, write_stream, _),
            ClientSession(read_stream, write_stream) as session,
        ):
            await session.initialize()
            tools = await session.list_tools()
            resources = await session.list_resources()
            prompts = await session.list_prompts()
        checks = [
            DiagnosticCheck("daemon_readiness", "pass", endpoint),
            DiagnosticCheck(
                "direct_mcp_discovery",
                "pass",
                "MCP discovery succeeded.",
                {"tools": len(tools.tools), "resources": len(resources.resources), "prompts": len(prompts.prompts)},
            ),
        ]
        error_log = await asyncio.to_thread(Path(os.devnull).open, "w")
        try:
            parameters = StdioServerParameters(
                command=sys.executable,
                args=[
                    "-m",
                    "global_memory.mcp.stdio_proxy",
                    "--endpoint",
                    endpoint,
                    "--token-file",
                    str(paths.auth_token),
                ],
            )
            async with (
                stdio_client(parameters, errlog=error_log) as (proxy_read, proxy_write),
                ClientSession(proxy_read, proxy_write) as proxy_session,
            ):
                await proxy_session.initialize()
                status = await proxy_session.call_tool("memory_status", {})
                if status.isError:
                    raise RuntimeError("stdio proxy status failed")
        finally:
            await asyncio.to_thread(error_log.close)
        checks.append(DiagnosticCheck("stdio_proxy", "pass", "stdio MCP status succeeded."))
        return checks
    except Exception as exc:
        return [
            DiagnosticCheck("daemon_readiness", "warn", "Daemon is unavailable.", {"reason": type(exc).__name__}),
            DiagnosticCheck("direct_mcp_discovery", "warn", "Skipped because the daemon is unavailable."),
            DiagnosticCheck("stdio_proxy", "warn", "Skipped because the daemon is unavailable."),
        ]


def _contract_check() -> DiagnosticCheck:
    discovery = load_discovery()
    hashes = {
        path.relative_to(contract_root()).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(contract_root().rglob("*.json"))
    }
    valid = len(discovery["tools"]) == 14 and len(discovery["resources"]) == 10 and len(discovery["prompts"]) == 6
    return DiagnosticCheck(
        "contract_hashes", "pass" if valid else "fail", f"{len(hashes)} contract files", {"sha256": hashes}
    )


async def run_diagnostics(settings: GlobalMemorySettings, paths: PlatformPaths) -> DiagnosticReport:
    checks = [DiagnosticCheck("configuration", "pass", "Configuration validated.")]
    checks.extend(_vault_checks(settings))
    checks.extend(_database_checks(paths))
    if callable(getattr(sqlite_vec, "load", None)):
        checks.append(DiagnosticCheck("vector_adapter", "pass", "sqlite-vec is importable."))
    else:
        checks.append(DiagnosticCheck("vector_adapter", "fail", "sqlite-vec is unavailable."))
    if settings.embeddings.enabled:
        try:
            async with httpx.AsyncClient(timeout=0.25) as provider_client:
                response = await provider_client.get(settings.embeddings.base_url.rstrip("/") + "/api/tags")
            available = response.status_code == 200 and settings.embeddings.model in json.dumps(response.json())
        except (httpx.HTTPError, ValueError):
            available = False
        checks.append(DiagnosticCheck("embedding_provider", "pass" if available else "warn", settings.embeddings.model))
    else:
        checks.append(DiagnosticCheck("embedding_provider", "pass", "Disabled; keyword mode remains available."))
    checks.extend(await _transport_checks(settings, paths))
    checks.append(_contract_check())
    for name, path in (
        ("claude_code_integration", Path.home() / ".claude/skills/global-memory"),
        ("codex_integration", Path.home() / ".agents/skills/global-memory"),
    ):
        checks.append(DiagnosticCheck(name, "pass" if path.exists() else "warn", str(path)))
    return DiagnosticReport(ok=not any(check.status == "fail" for check in checks), checks=checks)
