# Phase 12 report — watcher, persisted jobs, and recovery

## Completed requirements

The daemon now owns one watchdog observer whose callbacks marshal events back onto the daemon event loop before touching SQLite. Rapid changes are debounced by path, ignored support/excluded paths stay outside the queue, moves become an explicit delete plus upsert, and every flushed operation is persisted in `index_jobs` before execution. Index jobs are idempotent, retain completion/failure diagnostics, use exponential bounded retry for transient I/O, and isolate invalid notes or duplicate identities as terminal conflicts.

Startup reconciliation hashes canonical Markdown and compares it with live indexed documents. It queues new/changed files and missing paths, then drains due work. This closes the crash window after a Markdown write and makes database deletion recoverable without special restore logic. Opening generated state runs SQLite integrity checking; corrupt database/WAL state is quarantined with a timestamp and rebuilt from the Vault. The recovery event contains only the safe backup filename.

Embedding jobs now persist retry timing as well as attempts. Provider failures back off, stop at a configured maximum, remain visibly keyword-only, and do not block startup or keyword retrieval. A crash after provider work but before vector persistence is safe because the next eligible sync detects the missing content-hash/model row and retries the idempotent upsert.

The watcher starts and stops inside the Streamable HTTP application's lifespan. Uvicorn's normal signal shutdown therefore stops and joins the observer before process exit. Managed service E2E exercises that signal path.

## Files and tests

Migration 3 and corruption recovery live in `src/global_memory/index/database.py`. `jobs.py` owns persisted reconciliation and retry state; `watcher.py` owns Watchdog/debounce/event-loop handoff. The daemon reports real watcher and pending-job state.

`tests/integration/test_recovery_jobs.py` proves rapid-save coalescing, crash-after-write reconciliation, invalid/duplicate terminal isolation, corrupt-state quarantine, database deletion, and complete Markdown rebuild. Semantic integration tests prove retry delay and terminal bounds. A real daemon E2E performs three direct external note writes and observes only the final content becoming searchable through MCP.

## Commands and results

- Focused recovery/semantic/transport suite — 13 passed.
- `make check` — Ruff and strict mypy passed; 39 unit, 31 integration, 14 contract, and 6 E2E tests passed; deterministic contract regeneration passed.

## Known limitations and next phase

Embedding execution is currently an explicit sync service rather than a continuously scheduled daemon worker; persisted backoff and crash safety are in place. Phase 13 adds complete operational CLI coverage, doctor diagnostics, packaging verification, and native service installation.
