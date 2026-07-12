# Changelog

All notable changes are recorded here.

## Unreleased

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
