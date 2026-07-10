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
| 7 — Embeddings and vectors | Pending | |
| 8 — Retrieval and context | Pending | |
| 9 — MCP adapter | Pending | |
| 10 — Daemon and stdio proxy | Pending | |
| 11 — Obsidian workflow | Pending | |
| 12 — Watcher and recovery | Pending | |
| 13 — CLI, packaging, services, doctor | Pending | |
| 14 — Shared Agent Skill | Pending | |
| 15 — Claude Code integration | Pending | |
| 16 — Codex integration | Pending | |
| 17 — Security and performance | Pending | |
| 18 — V1 release acceptance | Pending | |
