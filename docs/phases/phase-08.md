# Phase 8 report — Hybrid retrieval, pagination, and context packing

## Completed requirements

Search supports keyword, semantic, hybrid, and metadata modes behind one application service. Default SQL candidate filtering includes only the resolved project plus active global/organization memory, preventing unrelated projects from consuming the candidate limit; no-project searches include only global/organization memory. Cross-project and candidate/archive/rejected/superseded content require explicit opt-in and receive labels. Tags, scopes, types, and statuses filter before keyword limits. Keyword and semantic ranks fuse through RRF, followed by bounded project/applicability, active/stale, importance, recency, and session-summary adjustments with explanation fields. Chunks group by document into one primary and bounded supporting passages. Results include every V1 source/rank/path/status/URI field.

Pagination uses a signed opaque keyset containing score, timestamp, ID, query fingerprint, and a strong ordered index snapshot—not an offset. Changed indexes reject stale cursors. Context packing round-robins note types, avoids duplicate documents, preserves sources and lifecycle/cross-project labels, identifies stored text as untrusted data, and fits the requested token budget in both structured and rendered forms.

## Files and tests

Retrieval is under `src/global_memory/retrieval/`; the FTS adapter gained pre-limit applicability and tag filters. Property tests cover RRF and cursor integrity. Integration tests cover project/no-project isolation, lifecycle opt-ins, cross-project labels, complete result fields, semantic-only discoveries, hybrid outage fallback, explicit semantic errors, metadata/tag filtering, document grouping, stable page traversal, snapshot invalidation, source attribution, diversity, and token budgets.

## Commands and results

- Phase tests first failed because retrieval modules did not exist.
- Initial tests passed; the completion audit then moved applicability/status/tag filtering before the FTS limit and replaced the weak count-based snapshot with ordered content/index state.
- `make check` — Ruff and strict mypy passed; 36 unit tests, 24 integration tests, and 9 contract tests passed before the final grouping regression; the final Phase 8 suite contains 7 passing retrieval integration tests. Transport E2E remains explicitly deferred to Phase 10.

## Known limitations and next phase

Semantic candidates are filtered after sqlite-vec KNN because the generated vector table intentionally carries no domain scope metadata; the candidate pool is bounded and configurable. Phase 9 maps the frozen V1 contract to these services through the official MCP SDK and proves discovery, every tool/resource/prompt, envelopes, and error translation in-process.
