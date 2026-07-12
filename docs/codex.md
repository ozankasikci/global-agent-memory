# Codex integration

The guided setup detects Codex and installs this integration automatically:

```shell
global-memory setup
```

To select Codex explicitly or repair only its managed integration:

```shell
global-memory setup --clients codex
global-memory integrations install codex
global-memory integrations status codex
global-memory integrations verify codex
```

The default installation symlinks the canonical skill and basic command skills under `~/.agents/skills/`. Use `--copy` when required. `--with-global-instructions` adds one marked block to `~/.codex/AGENTS.md`; unrelated instructions remain byte-preserved outside the block.

Basic skills:

```text
$gam-context <task>
$gam-search <query>
$gam-remember <durable knowledge>
$gam-review
$gam-dashboard
```

Run `/skills` in the Codex CLI to browse and select them, or type `$` to mention one directly. Codex custom prompts are deprecated, so the installer does not create legacy `/prompts:...` shims.

When the Codex CLI is available, registration uses its supported stdio command:

```shell
codex mcp add global-memory -- global-memory-mcp --endpoint http://127.0.0.1:8765/mcp/ --token-file <protected-token>
```

Codex clients share `~/.codex/config.toml`. The installer backs it up before invoking the CLI. If the executable is absent, a guarded and marked `[mcp_servers.global-memory]` block is appended; uninstall removes only that exact block. Unmanaged conflicts are never adopted or replaced.

After verification, ask Codex to **“Open the Global Agent Memory dashboard.”** The shared skill routes that request to `memory_dashboard_open`. The equivalent terminal command is `global-memory dashboard`.

```shell
global-memory integrations uninstall codex
```

References: [official Codex MCP documentation](https://developers.openai.com/codex/mcp) and [Codex skills](https://developers.openai.com/codex/codex-manual.md#customization-and-tooling).
