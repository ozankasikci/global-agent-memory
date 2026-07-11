# Operations

## Install and initialize

Install from a wheel or package index into an isolated Python 3.12+ environment, then initialize an absolute Vault:

```shell
global-memory init --vault "$HOME/Documents/Global Agent Memory"
global-memory config validate
global-memory doctor
```

Initialization is idempotent. It preserves existing README, templates, dashboards, and configuration, and creates the bearer token with user-only permissions.

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

`status`, `search`, `context`, `remember`, `get`, `approve`, `reject`, `update`, `supersede`, `archive`, `reindex`, and every `project` command call the shared daemon through MCP. Use `--endpoint`, `--token-file`, and `--config` to override platform defaults. Use `--show-completion` or `--install-completion` for shell completion.

## Diagnose and recover

```shell
global-memory doctor
global-memory doctor --json
global-memory reindex --full
```

Doctor checks configuration, Vault permissions/folders, Markdown validity and duplicate IDs, SQLite integrity/migrations/WAL/jobs, project resolution, vector and embedding state, daemon readiness, direct MCP discovery, stdio proxy calls, contract hashes, and client integration state. Provider and daemon outages are warnings when canonical Markdown remains healthy.

Generated SQLite/vector state can be deleted while the daemon is stopped. Startup reconciliation rebuilds it from Markdown and quarantines corrupt databases automatically.

## Backup, restore, upgrade, and rollback

```shell
global-memory backup "$HOME/Backups/global-memory.zip"
global-memory restore "$HOME/Backups/global-memory.zip" --vault "$HOME/Documents/Restored Memory"
global-memory upgrade
global-memory rollback 0.1.0
```

Backups contain the canonical Vault and a SHA-256 manifest, never the external token or generated indexes. Restore accepts only safe archive paths and an empty destination. Package upgrade/rollback uses pip from the active Python interpreter, or `uv pip --python` when the environment intentionally has no pip module. The Vault format and Markdown data are not removed by package changes.
