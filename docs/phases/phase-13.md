# Phase 13 report — CLI, diagnostics, packaging, and service operations

## Completed requirements

The CLI now exposes init, foreground serve, status, doctor, search, context, remember, get, approve, reject, update, supersede, archive, reindex, project CRUD/detection, config, daemon, MCP discovery/proxy, and integration status namespaces. Every runtime memory and project operation is a thin official-SDK MCP call; unit routing tests cover each frozen tool name and a real subprocess lifecycle creates then reads a memory through the daemon.

Doctor supports human and JSON output and checks configuration, Vault permissions and managed folders, invalid frontmatter, duplicate IDs, SQLite integrity/migration/WAL state, stale persisted jobs, unresolved projects, vector availability, embedding provider/model state, daemon readiness, direct MCP discovery, a real stdio-proxy `memory_status` call, every committed contract-file hash, and Claude Code/Codex installation targets. Expected local provider/daemon absence is a warning while durable Markdown remains healthy.

Administrative operations include manifest-hashed Vault backups, traversal-safe and integrity-checked restore into an empty destination, package upgrade and pinned rollback through active-interpreter pip or a uv-managed fallback, and shell completion through Typer. launchd and systemd-user renderers use native per-user paths, explicit config arguments, restart/auto-start declarations, managed markers, idempotent writes, and refusal to replace or remove unmanaged files. `install-service` loads/enables the native user service by default, while `uninstall-service` disables it before removing the managed file; both expose explicit opt-outs.

The wheel force-includes the frozen MCP V1 contract and installs all three console entry points. The upgrade fixture migrates generated state from schema 2 to 3 without losing prior records. `docs/operations.md` documents fresh initialization, service lifecycle, runtime commands, recovery, backup/restore, upgrade, and rollback.

## Files and tests

`src/global_memory/application/diagnostics_service.py` owns non-destructive doctor checks. `src/global_memory/operations.py` owns backup/restore, package changes, and native service artifacts. CLI command handlers remain adapters and do not import repositories or retrieval/index services for runtime operations.

Tests cover every CLI-to-MCP route, backup integrity and overwrite refusal, ZIP traversal, valid plist/systemd output, managed-file conflict behavior, package command construction, doctor offline behavior, doctor direct/stdin transport calls against a real daemon, schema upgrade, subprocess CLI lifecycle, and installation of a freshly built wheel in an isolated environment including contract discovery and console entry points.

## Commands and results

- `make check` — Ruff and strict mypy passed; 46 unit, 33 integration, 14 contract, and 9 E2E tests passed; deterministic contract regeneration passed.
- Fresh wheel rerun after console-entry assertions — 1 passed.

## Next phase

The integration namespace currently reports platform-aware installation state. Phases 14–16 add the canonical shared Agent Skill and its guarded Claude Code/Codex install, verify, and uninstall actions behind that existing CLI boundary.
