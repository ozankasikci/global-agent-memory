# Phase 0 report — Freeze MCP V1 contract

## Completed requirements

The V1 contract defines 14 tools, 10 resources, 6 client-neutral prompts, common success and error envelopes, stable error codes, defaults, cursor fields, mutation idempotency, examples, and compatibility rules. ADRs record the MCP-only and no-custom-REST decisions. Generated artifacts are deterministic and the discovery snapshot is marked frozen.

## Files and tests

Contract artifacts are under `contracts/mcp/v1/`; the generator is `scripts/generate_contract.py`; contract documentation and ADRs are under `docs/`. `tests/contract/test_contract_files.py` covers capability completeness, uniqueness, schema validity, valid and invalid examples, mutation request IDs, descriptions, and generated-file equivalence.

## Commands and results

- `python3 -m unittest tests.contract.test_contract_files` — failed first because discovery was missing, as intended.
- `python3 scripts/generate_contract.py` — generated committed artifacts.
- `uv run pytest tests/contract` — 9 passed.
- deterministic regeneration plus `cmp` — passed.

Format, lint, type-check, unit, integration, and E2E gates were introduced in Phase 1. No server existed yet, so live discovery was intentionally deferred to Phase 9.

## Known limitations and next phase

The contract has no backend implementation in this phase. Phase 1 creates the installable repository and baseline quality gates.
