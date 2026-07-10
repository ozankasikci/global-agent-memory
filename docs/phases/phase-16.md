# Phase 16 report — Codex integration

## Completed requirements

The same manager installs the exact canonical skill at `~/.agents/skills/global-memory`, optionally adds a marked and backed-up `~/.codex/AGENTS.md` block, and registers the stdio proxy through `codex mcp add global-memory -- ...`. The guarded fallback appends one marked `[mcp_servers.global-memory]` TOML block while preserving unrelated bytes; uninstall removes only an exact unchanged managed block.

Manifest, hash, copy/symlink, dry-run, force, conflict, status, verification, and uninstall behavior is identical to Claude Code. The real-daemon acceptance uses the same skill and server state and proves discovery, lifecycle cleanup, Git detection, and cross-project isolation for the Codex adapter.

## Evidence and live boundary

All fake-home and real-daemon adapter tests pass without reading or writing actual Codex settings. The Codex executable found on this machine currently fails before argument parsing because its npm wrapper references a missing bundled native binary (`ENOENT`). Repairing the user's Codex installation or editing their real config is outside this repository implementation and was not attempted.

`make check`: 46 unit, 39 integration, 16 contract, and 10 E2E tests passed with Ruff, strict mypy, and deterministic contract regeneration.

Reference: [official Codex MCP documentation](https://developers.openai.com/codex/mcp).
