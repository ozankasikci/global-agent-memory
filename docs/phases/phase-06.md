# Phase 6 report — Project registry and detection

## Completed requirements

Projects have stable IDs, canonical names, unambiguous aliases, absolute normalized roots, transport-neutral Git remotes, optional organizations, and explicit active state. The application supports list/get/add/update/deactivate. Detection resolves explicit input first, then the longest configured root, nearest Git-root facts and normalized origin, directory names/aliases, and finally no project. Unknown explicit projects return `PROJECT_NOT_FOUND`; no project is inferred from natural-language query text. SSH, `ssh://`, HTTP, and HTTPS forms normalize consistently.

## Files and tests

Project entities and registry ports are in `src/global_memory/projects/models.py`; Git normalization/discovery, SQLite registry, and detector are adjacent. `src/global_memory/application/project_service.py` exposes the use cases. Unit tests cover fixed and property-generated remote equivalence. Integration tests cover CRUD, aliases, update/deactivation, explicit precedence, nested root detection, real temporary Git repositories, remote-before-directory fallback, unknown paths, and missing explicit projects.

## Commands and results

- Phase tests first failed because project modules did not exist.
- `make check` — Ruff and strict mypy passed; 31 unit tests, 15 integration tests, and 9 contract tests passed; transport E2E remained explicitly deferred; contract regeneration was stable.

## Known limitations and next phase

Search scope explanations consume the detection result in Phase 8. Mutation request IDs for project-changing MCP calls are applied in the Phase 9 adapter using the common mutation store. Phase 7 adds optional embedding/vector adapters, changed-only work, model invalidation, retries, and mandatory keyword fallback.
