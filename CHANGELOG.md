# Changelog

All notable changes are recorded here.

## Unreleased

### Changed

- Publish the verified package to PyPI and make `uv tool install global-memory-mcp`
  the primary installation path.

## 0.1.4 - 2026-07-13

### Fixed

- Use stateless Streamable HTTP requests so long-lived Claude Code and Codex stdio
  bridges cannot retain an expired MCP session and fail later with
  `32600: Session terminated`.

## 0.1.3 - 2026-07-13

### Added

- Add an idempotent `global-memory setup` command that initializes the default Vault,
  installs the native user service, detects and connects supported coding agents,
  verifies healthy clients, handles broken client wrappers through the guarded fallback,
  and opens the authenticated dashboard after one confirmation.
- Add an architecture visual, real dashboard screenshots, feature comparison, measured
  10,000-memory performance evidence, community links, issue forms, a pull request
  template, and a code of conduct.
- Add dashboard component tests and adversarial coverage for malformed dashboard input,
  sealed-memory owner access, grant boundaries, stale policy, and hostile backup entries.

### Changed

- Make guided setup the primary README and operations path while keeping every
  individual initialization, service, integration, verification, and diagnostic
  command available for advanced use and repair.
- Modularize the Python source package into focused subpackages without changing the
  public CLI or MCP identifiers.
- Run dashboard component tests as part of the standard `make check` quality gate.
- Expand the README with Obsidian, dashboard, agent-skill, security, and repository
  discovery guidance.

### Fixed

- Wait for launchd to finish asynchronously unloading an existing managed service
  before bootstrapping its replacement during guided setup.
- Allow a populated Vault up to 60 seconds to finish startup reconciliation before
  guided setup reports the native service as unavailable.
- Refresh changed artifacts that are already recorded in the integration manifest when
  guided setup repairs or upgrades a client, while continuing to refuse unmanaged paths.
- Allow fresh guided setup to install a client integration without incorrectly treating
  the first install as a forced replacement.
- Reject probable secrets and symlinked Markdown even when notes are added directly to
  the Vault outside the MCP workflow.
- Create backups atomically outside the Vault and restore only after complete manifest,
  path, link, size, and checksum validation.
- Return structured `NOTE_INVALID` dashboard responses for malformed or non-object JSON
  instead of allowing parser exceptions to escape.

## 0.1.2 - 2026-07-12

### Added

- Add managed `gam-context`, `gam-search`, `gam-remember`, `gam-review`, and `gam-dashboard` skills for Claude Code and Codex, including safe installer upgrades, validation, packaging, and client-specific usage docs.

### Changed

- Refresh the dashboard with the new component-based layout across overview, access, memories, projects, and system views.

### Fixed

- Detect broken client CLI wrappers before registration and use the guarded configuration fallback when the executable is present but unusable.
- Keep the dashboard background uniform across full-height and embedded browser hosts.

## 0.1.1 - 2026-07-12

### Fixed

- Return a structured `NOTE_INVALID` response for unsupported `memory_remember` types instead of leaking a non-serializable validator exception.
- Scope dashboard activity to the selected project, including safe attribution for future hard-deleted audit events.

### Changed

- Enumerate the closed V1 memory types in MCP discovery and CLI help so agents and people can choose a valid type without trial and error.
- Replace the minimal repository README with a complete installation, usage, architecture, security, MCP, and contributor guide.

### Added

- Add owner-controlled Protected and Sealed memory access with exact-scope temporary grants, permission and duration downgrades, live policy revocation, and dashboard approval controls.
- Add a ShadCN/TypeScript local dashboard for project overview, candidate review and editing, duplicate/conflict comparison, search, activity, and system health; expose secure launch through both `global-memory dashboard` and the `memory_dashboard_open` MCP tool.
- Rename the product to Global Agent Memory while retaining the V1 `global-memory` CLI, package, configuration, Python, skill, and MCP identifiers for backward compatibility.
- Freeze the MCP V1 discovery contract, schemas, prompts, resources, examples, and stable error codes.
- Add the installable Python package and baseline quality gates.
- Add validated configuration precedence, platform-native generated-state paths, safe Vault initialization, and protected local token creation.
- Add adapter-independent memory models and lifecycle rules, loss-conscious Markdown round trips, safe canonical routing, atomic Vault writes, optimistic concurrency, and content-free audit events.
- Add disposable SQLite migrations, deterministic structural chunks, FTS5 and metadata retrieval, incremental move/delete handling, conflict quarantine, diagnostics, and rebuild support.
- Add candidate duplicate detection, explicit section patches, reciprocal supersession with rollback, archive and hard-delete separation, content-free tombstones, change notifications, and durable request-ID replay receipts.
- Add a normalized project registry with aliases, roots, remotes, organization metadata, deactivation, and priority-ordered working-directory/Git detection.
- Add optional batched Ollama embeddings, deterministic fakes, sqlite-vec cosine storage, changed-only indexing, model/dimension invalidation, persisted retry jobs, stale-vector pruning, and keyword-only degradation.
- Add scoped keyword/semantic/hybrid/metadata retrieval with RRF, explainable bounded adjustments, grouped passages, lifecycle labels, snapshot-bound keyset cursors, and diverse token-budgeted context.
- Add the complete frozen MCP V1 application adapter with self-contained discovery schemas, all tools/resources/prompts, common envelopes, stable errors, runtime project detection, and official SDK client contract tests.
- Add the authenticated localhost Streamable HTTP daemon, bounded requests/connections, verified managed lifecycle, protocol-transparent stdio proxy, stable unavailable behavior, and CLI runtime calls through MCP.
- Add idempotent Obsidian templates, Bases dashboards, review guidance, project overview hubs, path-stable visual links, and support-asset-aware indexing.
- Add persisted/debounced watcher jobs, startup reconciliation, bounded retry schedules, generated-database corruption quarantine and Markdown rebuild, and graceful daemon watcher shutdown.
- Add the complete MCP-routed runtime CLI, doctor diagnostics, foreground and managed service operation, native launchd/systemd user files, shell completion, verified backup/restore, upgrade/rollback, and self-contained wheel packaging.
- Add the canonical client-neutral Global Agent Memory Agent Skill with bounded V1 reference material, durable-memory workflow, project isolation, optimistic lifecycle rules, source citation, and security constraints.
- Add guarded Claude Code and Codex installers with canonical skill symlink/copy modes, preferred official CLI registration, backed-up config fallbacks, managed instruction snippets, manifests, status/verify/uninstall, and shared-daemon isolation acceptance.
- Add release threat modeling, probable-secret rejection, recursive structured-log redaction, malicious-note and traversal hardening tests, and a recorded 10,000-note plus HTTP/stdio performance regression suite.
- Wire configured embeddings and vectors into the shared daemon with changed-note resync and keyword-only outage degradation; add combined V1 cross-client, Obsidian-equivalent, semantic, concurrency, crash-recovery, and generated-state rebuild acceptance.
