# Claude Code integration

Initialize and start Global Agent Memory first, then install at user scope:

```shell
global-memory integrations install claude-code
global-memory integrations status claude-code
global-memory integrations verify claude-code
```

The default installation symlinks the canonical skill and basic command skills under `~/.claude/skills/`. Use `--copy` when symlinks are unsuitable. `--with-global-instructions` adds one marked block to `~/.claude/CLAUDE.md`; unrelated content is preserved. `--dry-run` previews and `--json` returns machine-readable output.

Basic commands:

```text
/gam-context <task>
/gam-search <query>
/gam-remember <durable knowledge>
/gam-review
/gam-dashboard
```

Claude Code discovers these as skills and exposes them directly in the `/` menu. `gam-remember` and `gam-dashboard` are manual-only because they create a candidate or open a browser session. The other shortcuts may also be selected automatically when their descriptions match.

When `claude` is installed, registration uses the supported user-scoped command shape:

```shell
claude mcp add global-memory --scope user -- global-memory-mcp --endpoint http://127.0.0.1:8765/mcp/ --token-file <protected-token>
```

The installer backs up the user config first. If the CLI is unavailable, it makes a guarded `mcpServers` edit in the backed-up user JSON. Existing unmanaged skill or server entries are refused, including with `--force`. Force applies only to a changed artifact already recorded in the integration manifest.

After verification, tell Claude Code: **“Open the Global Agent Memory dashboard.”** The installed skill instructs it to call `memory_dashboard_open`, which creates a short-lived authenticated browser session. You can always use `global-memory dashboard` directly from a terminal.

Uninstall removes only recorded, still-matching artifacts:

```shell
global-memory integrations uninstall claude-code
```

References: [Claude Code MCP documentation](https://docs.anthropic.com/en/docs/claude-code/mcp) and [Claude Code skills](https://code.claude.com/docs/en/slash-commands).
