# Operations

## Install and initialize

Install into an isolated Python 3.12+ environment, then run the guided setup:

```shell
uv tool install git+https://github.com/ozankasikci/global-agent-memory.git
global-memory setup
```

`setup` displays one plan and asks once before it changes anything. By default it uses
`~/Documents/Global Agent Memory`, installs the native launchd or systemd user service,
connects detected Claude Code and Codex installations, runs live verification for
healthy clients, and opens the dashboard. It is idempotent and preserves unrelated
client configuration.

Useful setup variants:

```shell
global-memory setup --dry-run
global-memory setup --yes
global-memory setup --vault "$HOME/Memory"
global-memory setup --clients claude-code
global-memory setup --clients none --no-service --no-open-dashboard
```

When an existing configuration is present, `--vault` must match its configured Vault.
Setup never silently repoints an installation. A detected but unhealthy client
executable uses the guarded configuration fallback and is reported as not live-verified.

For manual installation or repair, the individual commands remain available:

```shell
global-memory init --vault "$HOME/Documents/Global Agent Memory"
global-memory config validate
global-memory daemon install-service --kind launchd  # use systemd on Linux
global-memory integrations install all
global-memory integrations verify all
global-memory doctor
```

Initialization preserves existing README, templates, dashboards, and configuration,
and creates the bearer token with user-only permissions.

## Run the service

For an interactive foreground process:

```shell
global-memory serve
```

For explicit managed-process control:

```shell
global-memory daemon start
global-memory daemon status
global-memory daemon stop
```

Install an auto-start file at the native per-user location:

```shell
global-memory daemon install-service --kind launchd
# Linux alternative:
global-memory daemon install-service --kind systemd
```

The command refuses to replace an unmanaged service file, then loads/enables the per-user service immediately. The launchd plist uses `RunAtLoad`/`KeepAlive`; the systemd user unit uses `WantedBy=default.target`. Use `--no-enable` when you only want to inspect the generated file. `uninstall-service` stops/disables the service before removing its managed file; use `--no-disable` only when native service state is managed separately.

## Runtime commands

`status`, `dashboard`, `search`, `context`, `remember`, `get`, `approve`, `reject`, `update`, `supersede`, `archive`, `reindex`, and every `project` command call the shared daemon through MCP. Use `--endpoint`, `--token-file`, and `--config` to override platform defaults. Use `--show-completion` or `--install-completion` for shell completion.

## Review dashboard

```shell
global-memory dashboard
# Print a single-use URL without opening a browser:
global-memory dashboard --no-open
```

The dashboard provides project overview, one-at-a-time candidate review and editing, duplicate/conflict comparison, memory search, access-request approval, temporary grant revocation, audited sealed-memory unlocks, project switching, system status, reindexing, timestamped Vault backups, and links to canonical Markdown. The launch URL expires after 60 seconds, can be exchanged only once, and creates a local HttpOnly session. Do not share the URL. The UI is served only by the localhost daemon and its private JSON endpoints are not a public integration contract.

Visibility is fail-closed across MCP tools and resources:

- **Standard** memories participate in normal retrieval.
- **Protected** memories may produce only the neutral warning `protected_memory_may_be_relevant`. An agent calls `memory_access_request`, waits while the owner reviews it in **Access**, polls `memory_access_status`, and passes the returned `access_grant` to the supported read/edit/manage tool.
- **Sealed** memories are not indexed by body and cannot be retrieved by agents. The owner may unlock one dashboard view; that access is recorded.

Access grants are purpose-, project-, permission-, memory-, and duration-scoped. The owner selects the exact protected matches, may downgrade but never elevate the requested permission, and may shorten but never extend the requested duration. A protected memory may set a Read/Edit/Manage maximum, restrict eligible projects, and force approval for every retrieval. One-retrieval grants are consumed on first use; other grants can be revoked immediately. Tightening a memory policy revokes incompatible active grants. Agents can request and poll, but cannot approve, deny, or revoke. Never store credentials, passwords, private keys, or API keys in memory, including sealed memory.

## Diagnose and recover

```shell
global-memory doctor
global-memory doctor --json
global-memory reindex --full
```

Doctor checks configuration, Vault permissions/folders, Markdown validity and duplicate IDs, SQLite integrity/migrations/WAL/jobs, project resolution, vector and embedding state, daemon readiness, direct MCP discovery, stdio proxy calls, contract hashes, and client integration state. Provider and daemon outages are warnings when canonical Markdown remains healthy.

Generated SQLite/vector state can be deleted while the daemon is stopped. Startup reconciliation rebuilds it from Markdown and quarantines corrupt databases automatically.

### Recover from a closed MCP transport

Current GAM daemons use stateless Streamable HTTP requests, so an idle coding-agent
bridge does not retain an expiring server session. After upgrading from an older
installation, restart Claude Code or Codex once so it launches the updated
`global-memory-mcp` bridge. If a client still reports `32600: Session terminated` or
`Transport closed`, verify both layers:

```shell
global-memory daemon status
global-memory doctor
global-memory integrations verify all
```

Do not interpret a transport failure as an empty memory result. Reconnect first, then
repeat `memory_search`; only a successful search response is authoritative about
whether a matching memory exists.

## Backup, restore, upgrade, and rollback

```shell
global-memory backup "$HOME/Backups/global-memory.zip"
global-memory restore "$HOME/Backups/global-memory.zip" --vault "$HOME/Documents/Restored Memory"
global-memory upgrade
global-memory rollback 0.1.0
```

Backups contain the canonical Vault and a SHA-256 manifest, never the external token or generated indexes. Restore accepts only safe archive paths and an empty destination. Package upgrade/rollback uses pip from the active Python interpreter, or `uv pip --python` when the environment intentionally has no pip module. The Vault format and Markdown data are not removed by package changes.
