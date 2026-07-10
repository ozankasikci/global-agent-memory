# Codex integration

Initialize and start Global Memory first, then install:

```shell
global-memory integrations install codex
global-memory integrations status codex
global-memory integrations verify codex
```

The default installation symlinks the same canonical skill to `~/.agents/skills/global-memory`. Use `--copy` when required. `--with-global-instructions` adds one marked block to `~/.codex/AGENTS.md`; unrelated instructions remain byte-preserved outside the block.

When the Codex CLI is available, registration uses its supported stdio command:

```shell
codex mcp add global-memory -- global-memory-mcp --endpoint http://127.0.0.1:8765/mcp/ --token-file <protected-token>
```

Codex clients share `~/.codex/config.toml`. The installer backs it up before invoking the CLI. If the executable is absent, a guarded and marked `[mcp_servers.global-memory]` block is appended; uninstall removes only that exact block. Unmanaged conflicts are never adopted or replaced.

```shell
global-memory integrations uninstall codex
```

Reference: [official Codex MCP documentation](https://developers.openai.com/codex/mcp).
