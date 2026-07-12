# Phase 5 report — Lifecycle application service and idempotency

## Completed requirements

Candidate creation checks normalized exact content and close title/body matches within the applicable scope, returns IDs/titles/excerpts, refuses likely duplicates, and requires explicit `force`. Application mutations support metadata and section patches, approve/reject routing, archive/forget, explicit hard delete with a content-free tombstone, and reciprocal supersession. Multi-file supersession restores both originals when an ordinary write fails. Optional change notifications provide the indexing trigger without coupling the application layer to SQLite. Mutation receipts persist the operation, canonical payload hash, and original result; identical retries replay the original result without repeating writes or notifications, while changed payloads return `REQUEST_ID_CONFLICT`.

## Files and tests

The lifecycle orchestration is in `src/global_memory/application/memory_service.py`; repository ports and results are under `src/global_memory/domain/`; Vault mutations are in `src/global_memory/vault/repository.py`; SQLite receipts are in `src/global_memory/index/mutations.py`. Integration tests cover exact/close/forced candidates, same/different request-ID retries, patch preservation, notifications, reciprocal supersession/replay, archive/forget, hard deletion, and tombstone redaction. Unit failure injection covers second-write supersession rollback.

## Commands and results

- Phase tests first failed because the mutation store and expanded service did not exist.
- `make check` — Ruff and strict mypy passed; 26 unit tests, 11 integration tests, and 9 contract tests passed; transport E2E remained explicitly deferred; contract regeneration was stable.

## Known limitations and next phase

Crash recovery between a Vault write and mutation-receipt persistence is handled by persisted jobs/startup reconciliation in Phase 12. The daemon will serialize mutations in Phase 10. Phase 6 adds the project registry, path/Git detection priority, aliases, and SSH/HTTPS remote normalization.
