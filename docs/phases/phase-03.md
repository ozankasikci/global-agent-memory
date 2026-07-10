# Phase 3 report — Domain model and Markdown repository

## Completed requirements

The domain validates required metadata, project scope, confidence and importance bounds, timezone-aware timestamps, temporal order, active supersession invariants, and supported tool-created types while preserving unknown parsed types and YAML properties. Markdown parsing preserves the body exactly. Canonical routing covers lifecycle, scope, and type. Vault paths reject absolute paths, traversal, and symlink escapes. Writes use sibling temporary files, flush/fsync, and atomic replace. Updates require an exact version and protect identity, creation time, and lifecycle fields. Application services drive create/read/update/approve/reject/archive through a repository protocol. Audit records contain identifiers and safe metadata, never note bodies.

## Files and tests

Domain and ports are under `src/global_memory/domain/`; the application boundary is `src/global_memory/application/memory_service.py`; Vault adapters are under `src/global_memory/vault/`. `tests/unit/test_domain_and_markdown.py` and `tests/unit/test_vault_repository.py` cover validation, unknown properties/types, complex Markdown, property-based Unicode round trips, confinement, symlinks, routing, duplicates, immutable fields, stale writes, atomic failure, lifecycle transitions, application operations, and audit redaction.

## Commands and results

- Phase tests initially failed because domain modules were absent.
- The property test then exposed U+0085 normalization by plain YAML scalars; quoted string emission fixed the loss and retained the regression.
- `uv run pytest tests/unit/test_domain_and_markdown.py tests/unit/test_vault_repository.py` — 14 passed.
- `make check` — Ruff and strict mypy passed; 22 unit tests, integration, and 9 contract tests passed; transport E2E remained explicitly deferred; contract regeneration was stable.

## Known limitations and next phase

Cross-file lifecycle moves use rollback on ordinary failures; startup crash reconciliation is Phase 12. Duplicate detection beyond immutable IDs and request idempotency are Phase 5. Phase 4 adds disposable SQLite migrations, deterministic chunking, FTS, moves/deletes, rebuild, and integrity checks.
