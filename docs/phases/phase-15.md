# Phase 15 report — Claude Code integration

## Completed requirements

The shared integration manager installs the canonical skill at `~/.claude/skills/global-memory` by symlink or copy, records its tree hash and mode, and refuses unmanaged or modified conflicts. It prefers the official `claude mcp add ... --scope user -- <stdio command>` mechanism. The user configuration is backed up before registration; when the executable is unavailable, a guarded JSON adapter preserves unrelated keys and owns only the exact `mcpServers.global-memory` value.

The optional CLAUDE.md instruction is explicitly gated, marked, idempotent, hashed, backed up, and removed only when unchanged. The protected manifest records every installed path, mode, hash, backup, registration mode, and proxy command. Status checks availability, skill integrity, and registration. Uninstall touches only recorded matching artifacts.

Verification checks client availability, installed skill hash, MCP registration, exact tool/resource/prompt discovery, `memory_status`, candidate create/read/reject cleanup, project detection from temporary Git repositories, and cross-project isolation through the real daemon.

## Evidence and live boundary

Fake-home tests prove copy/symlink install, idempotency, unmanaged and modified conflict refusal, config preservation, snippet markers, backups, dry-run, force boundaries, guarded fallback, and uninstall. The shared real-daemon E2E passes with a fake client-registration adapter, so tests do not alter actual user configuration.

Live Claude Code installation was intentionally not performed because it would mutate the user's real user-scoped client configuration. The implementation and command are documented for explicit execution.

`make check`: 46 unit, 39 integration, 16 contract, and 10 E2E tests passed with Ruff, strict mypy, and deterministic contract regeneration.

Reference: [Claude Code MCP documentation](https://docs.anthropic.com/en/docs/claude-code/mcp).
