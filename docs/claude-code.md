# Claude Code integration

Initialize and start Global Memory first, then install at user scope:

```shell
global-memory integrations install claude-code
global-memory integrations status claude-code
global-memory integrations verify claude-code
```

The default installation symlinks the canonical skill to `~/.claude/skills/global-memory`. Use `--copy` when symlinks are unsuitable. `--with-global-instructions` adds one marked block to `~/.claude/CLAUDE.md`; unrelated content is preserved. `--dry-run` previews and `--json` returns machine-readable output.

When `claude` is installed, registration uses the supported user-scoped command shape:

```shell
claude mcp add global-memory --scope user -- global-memory-mcp --endpoint http://127.0.0.1:8765/mcp/ --token-file <protected-token>
```

The installer backs up the user config first. If the CLI is unavailable, it makes a guarded `mcpServers` edit in the backed-up user JSON. Existing unmanaged skill or server entries are refused, including with `--force`. Force applies only to a changed artifact already recorded in the integration manifest.

Uninstall removes only recorded, still-matching artifacts:

```shell
global-memory integrations uninstall claude-code
```

Reference: [Claude Code MCP documentation](https://docs.anthropic.com/en/docs/claude-code/mcp).
