# Phase 18 report — final automated V1 acceptance

## Architecture gap found and fixed

The release audit found that embedding providers, changed-only indexing, sqlite-vec, and hybrid retrieval were implemented but not wired into the shared daemon container. The daemon now constructs the configured Ollama provider (or deterministic test provider), syncs changed chunks into vectors at startup, after MCP writes, and after watcher jobs, and passes provider/vector adapters to `SearchService`. Provider failure persists retry work and keeps keyword/lifecycle operation available; it does not prevent readiness.

## Automated acceptance

New combined E2E uses an HTTP session as the Claude-side client and an independent stdio-proxy session as the Codex-side client. It creates a candidate, edits the Markdown as Obsidian would, observes the watcher update, approves it, reads the edited body from the second client, performs exact and semantic retrieval, and verifies configured semantic status. Two concurrent stale updates produce exactly one success and one `VERSION_CONFLICT`. Exact request replay returns one identity and a changed payload returns `REQUEST_ID_CONFLICT`.

A recovery E2E kills the daemon immediately after an external Markdown write, restarts, and proves startup reconciliation indexes the durable edit. It then deletes SQLite/WAL/SHM, restarts again, and proves equivalent visible memory rebuilds from Markdown. Existing combined tests cover two Git projects with no leakage, unavailable-provider keyword fallback, complete discovery, lifecycle exclusion, security boundaries, both installer manifests, native visual assets, and fresh-wheel operation.

Final `make check` passed with Ruff, strict mypy, 54 unit tests, 40 integration tests, 16 contract tests, 12 real E2E tests, and deterministic contract regeneration. A final shared-container offline-degradation integration test then raised the integration total to 41 and the gated in-process coverage to 87.56%.

The detailed scenario/gate map is in `docs/release-checklist-v1.md`. `docs/testing.md` distinguishes normal, performance, and explicitly authorized live tests.

## Release status

Automated acceptance is complete, but Phase 18 and V1 tagging remain blocked by gates that cannot be truthfully completed inside the repository test harness:

1. The configured remote Ubuntu/macOS and Python 3.12/3.14 CI matrix has not produced a run in this local-only session.
2. Live Claude Code install/invocation/uninstall and live Obsidian properties/Bases/graph inspection would alter actual user-scoped state and require explicit permission.
3. The locally discovered Codex npm wrapper fails with `ENOENT` because its bundled native executable is missing; live Codex acceptance requires repairing that external installation first.

No V1 tag was created. The product implementation is release-candidate complete subject to those recorded external/manual gates.
