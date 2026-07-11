# Global Agent Memory

Global Agent Memory is a local-first, project-aware durable memory service for MCP-compatible coding agents. Markdown notes in an Obsidian Vault are canonical; SQLite, FTS, vectors, jobs, and caches are generated state that can be rebuilt.

The V1 technical identifiers remain `global-memory`, `global-memory-mcp`, `global-memoryd`, `global_memory`, and `product: global-memory` for backward compatibility. The product, Vault, and repository use the **Global Agent Memory** name.

The project is being implemented in the ordered phases documented in [`docs/global-memory-implementation-plan(1).md`](docs/global-memory-implementation-plan(1).md). The frozen V1 discovery contract lives in [`contracts/mcp/v1/discovery.json`](contracts/mcp/v1/discovery.json).

## Development

Python 3.12+ and `uv` are required.

```shell
uv sync
make check
uv run global-memory --version
```

Runtime memory operations will use the MCP path. No client reads the Vault or generated SQLite index directly.

Open the private review dashboard after the daemon is running:

```shell
global-memory dashboard
```

Claude Code, Codex, and other MCP clients can open the same authenticated dashboard with the `memory_dashboard_open` tool when you ask them to “open the memory dashboard.”

See [operations](docs/operations.md) for initialization, daemon/service management, diagnostics, backup/restore, upgrades, and the complete MCP-routed CLI.

Client setup: [Claude Code](docs/claude-code.md) and [Codex](docs/codex.md).

Testing and release status: [testing](docs/testing.md) and [V1 release checklist](docs/release-checklist-v1.md).
