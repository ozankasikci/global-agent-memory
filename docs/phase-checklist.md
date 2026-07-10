# Phase completion checklist

| Phase | Status | Evidence |
| --- | --- | --- |
| 0 — MCP V1 contract | Complete | Contract unit tests and deterministic regeneration pass. |
| 1 — Repository and quality gates | Complete | Package import, CLI version, lint, mypy, unit, contract, and baseline check pass. |
| 2 — Configuration and Vault initialization | Complete | Precedence, validation, idempotency, token-mode, overwrite-safety, and state-separation tests pass. |
| 3 — Domain and Markdown repository | Complete | Domain, Markdown, routing, confinement, atomic-write, concurrency, lifecycle-service, and audit tests pass. |
| 4 — SQLite, chunking, and FTS | Complete | Migration, WAL/FK, chunking, full/incremental, exact/phrase/Unicode/metadata search, move/delete, duplicate, invalid-note, and rebuild tests pass. |
| 5 — Lifecycle and idempotency | Complete | Duplicate/force, patch, approve/reject, reciprocal rollback-safe supersede, archive/hard-delete, notifications, replay, and request-conflict tests pass. |
| 6 — Project registry and detection | Complete | CRUD/deactivation, aliases, explicit/root/Git-remote/directory/none priority, nested paths, and SSH/HTTPS normalization tests pass. |
| 7 — Embeddings and vectors | Complete | Fake/Ollama, retries, real sqlite-vec, changed-only, model/dimension invalidation, stale pruning, pending jobs, and keyword-fallback tests pass. |
| 8 — Retrieval and context | Complete | Scoped SQL filtering, RRF, bounded ranking, grouping, lifecycle/cross-project labels, metadata/tags, semantic fallback, keyset cursors, and bounded diverse context tests pass. |
| 9 — MCP adapter | Complete | Official in-memory SDK client proves exact discovery, every tool/resource/prompt, envelopes, lifecycle/idempotency, working-directory isolation, and outside-Vault rejection. |
| 10 — Daemon and stdio proxy | Complete | Authenticated localhost Streamable HTTP, SDK host/origin validation, request/connection limits, verified daemon lifecycle, protocol-pure stdio, two-client shared state, stable unavailable errors, and CLI-over-MCP E2E tests pass. |
| 11 — Obsidian workflow | Complete | Eight idempotent templates, three valid Bases dashboards covering all required views, review docs, project hubs, visual graph links, support-file index exclusion, and lifecycle/link tests pass. |
| 12 — Watcher and recovery | Complete | Persisted debounced jobs, startup reconciliation, watcher-driven external edits, bounded index/embedding retries, invalid/duplicate isolation, corruption quarantine, Markdown rebuild, and signal-driven daemon shutdown tests pass. |
| 13 — CLI, packaging, services, doctor | Complete | Complete MCP-routed runtime/project CLI, serve/daemon/MCP/config/integration namespaces, doctor, shell completion, safe backup/restore, upgrade/rollback, managed launchd/systemd files, upgrade fixture, subprocess lifecycle, and fresh-wheel tests pass. |
| 14 — Shared Agent Skill | Complete | Canonical scaffold-validator-clean client-neutral skill covers before-work retrieval, project isolation, search/write/update/lifecycle/completion/security rules, frozen-capability references, examples, and separate skill/contract versions. |
| 15 — Claude Code integration | Complete | Fake-home symlink/copy install, official user-scope CLI registration adapter, guarded JSON fallback, manifest/backups, optional snippet, status/verify/uninstall, conflict/idempotency, and shared-daemon verification pass; real user config was not mutated. |
| 16 — Codex integration | Complete | Fake-home symlink/copy install, official CLI registration adapter, marked TOML fallback, manifest/backups, optional AGENTS snippet, status/verify/uninstall, conflict/idempotency, and shared-daemon verification pass; local Codex binary is broken so live acceptance is deferred. |
| 17 — Security and performance | Complete | Threat model, secret rejection, recursive log redaction, malicious YAML/prompt-injection/traversal/auth/size tests, localhost controls, config ownership safety, and opt-in 10k-note/HTTP/stdio performance budgets pass. |
| 18 — V1 release acceptance | Blocked on live gates | Automated cross-client/Obsidian-equivalent/semantic/offline/rebuild/concurrency/recovery/contract/skill/security scenarios pass. Tagging awaits remote CI, explicitly authorized Claude/Obsidian live checks, and repair of the broken local Codex CLI binary. |
