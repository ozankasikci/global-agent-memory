# Phase 7 report — Embedding and vector adapters

## Completed requirements

Embedding providers and vector stores are replaceable protocols. Tests use deterministic normalized fake embeddings and an in-memory fake vector store. The Ollama adapter batches through `/api/embed`, applies timeouts and bounded retries, validates counts/dimensions, and returns a safe retryable error without exposing input. The preferred sqlite-vec adapter loads the extension with protected extension loading, stores cosine vectors in dimension-specific generated tables, and joins stable chunk mappings. Embedding work skips unchanged hash/provider/model/dimension combinations, invalidates prior models and dimensions, prunes replaced chunks, persists pending attempts, and reports keyword-only degradation.

## Files and tests

Providers are under `src/global_memory/embeddings/`; vector and embedding-index adapters are under `src/global_memory/index/`. Migration 2 adds retry jobs and vector mappings. Unit tests cover deterministic fakes, batching, retry success, and safe outage errors. Integration tests load sqlite-vec 0.1.9, assert cosine ordering, changed-only skips, model/dimension invalidation, stale-vector pruning, pending attempts, and successful keyword retrieval during semantic outage.

## Commands and results

- Phase tests first failed because semantic adapters did not exist.
- `uv sync` installed the stable `sqlite-vec==0.1.9` release under the constrained `<0.2` adapter boundary.
- Initial tests passed, then the completion audit identified stale dynamic rows and same-model dimension drift; pruning and dimension-aware invalidation were added with regressions.
- `make check` — Ruff and strict mypy passed; 34 unit tests, 18 integration tests, and 9 contract tests passed; transport E2E remained explicitly deferred; contract regeneration was stable.

## Known limitations and next phase

sqlite-vec is pre-V1 and exact/ANN evolution remains encapsulated. Phase 8 combines FTS and vector candidates using RRF, applies default project/status rules, adds opaque cursor pagination, explanation fields, grouping, and token-budgeted context packing.
