# Phase 4 report — SQLite migrations, chunking, and FTS

## Completed requirements

The generated SQLite index starts with a forward migration containing documents, chunks, FTS5, links, logical embeddings, projects, index events, mutation requests, and migration state. WAL and foreign keys are enabled. Chunking is deterministic, carries heading context, prefers structural boundaries, retains bounded overlap, keeps fenced code intact below a hard ceiling, and uses a replaceable estimator. Full and per-path indexing support unchanged skips, edits, moves, deletion tombstones, invalid-note isolation, and duplicate-ID quarantine. Keyword retrieval covers exact IDs, exact phrases, Unicode, project/status/type/scope filters, while metadata retrieval covers tags without FTS terms. Rebuilds derive equivalent visible results from Markdown.

## Files and tests

Implementation is under `src/global_memory/index/`. Unit coverage in `tests/unit/test_chunking.py` verifies stable ordinals/hashes, heading context, code boundaries, and the hard ceiling. `tests/integration/test_indexing.py` verifies migration state, WAL/FK, exact/phrase/Unicode/metadata queries, full rebuild equivalence, incremental edit/move/delete, tombstones, copied IDs, invalid-note diagnostics, and searchable-result quarantine.

## Commands and results

- Phase tests first failed because index modules were missing.
- The first implementation run exposed an `executescript` transaction boundary; migration now owns an explicit atomic script transaction.
- The hard-ceiling regression initially exposed double overlap; overlap is now bounded by the ceiling.
- `make check` — Ruff and strict mypy passed; 25 unit tests, 6 integration tests, and 9 contract tests passed; transport E2E remained explicitly deferred; contract regeneration was stable.

## Known limitations and next phase

Semantic vectors are intentionally Phase 7 and watcher-driven indexing is Phase 12. Phase 5 adds duplicate candidate checks, lifecycle orchestration, reciprocal supersession, archive/hard-delete separation, and mutation-request idempotency.
