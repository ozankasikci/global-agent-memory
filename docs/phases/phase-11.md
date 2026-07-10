# Phase 11 report — Obsidian visual workflow

## Completed requirements

Vault initialization now installs all eight requested templates without replacing existing files. Templates expose the canonical V1 properties and create reviewable candidates. Three native Obsidian Bases files provide eleven views covering the required candidate queue, decisions grouped by project, verified solutions, recent updates, superseded/rejected/archived memories, low-confidence notes, unresolved visual links, safely representable validation conflicts, and project-specific memories.

The dashboard index embeds the primary views and links to candidate review instructions. The guide explains approve/reject, optimistic concurrency, protected lifecycle fields, watcher behavior, and secret exclusion. Project-scoped writes create a stable, non-destructive project overview hub and add a project wikilink. Managed notes have ID aliases and visual wikilinks; superseded and replacement notes link reciprocally by basename, so canonical lifecycle folder moves do not invalidate those links. Explicit semantic links are never invented.

README, Templates, Dashboards, and generated project overview files are recognized as support assets rather than invalid managed memories. Full rebuilds therefore report only actual malformed memory notes. Obsidian URI behavior remains contract-tested and percent-encodes the Vault and relative path.

## Files and tests

`src/global_memory/vault/obsidian.py` owns templates, current Bases YAML, review docs, dashboard installation, and project hubs. `is_managed_memory_path` centralizes the memory/support-file boundary for the repository and indexer.

`tests/unit/test_obsidian_assets.py` parses every generated template and Base as YAML, validates canonical property references and every required view, checks review instructions, and proves idempotent preservation of user edits. Repository tests prove project links survive candidate-to-active moves and reciprocal supersession links resolve to stable basenames. An integration test proves visual assets do not inflate invalid-memory diagnostics.

## Commands and results

- `uv run pytest -q tests/unit/test_obsidian_assets.py tests/unit/test_vault_repository.py tests/integration/test_indexing.py` — 18 passed.
- `make check` — Ruff and strict mypy passed; 39 unit, 26 integration, 14 contract, and 5 E2E tests passed; deterministic contract regeneration passed.

## Manual acceptance boundary and next phase

Obsidian is installed on this machine, but this phase did not open or mutate the user's active Obsidian session. Generated files are validated against the current documented Bases YAML schema and are ready for visual inspection in a temporary or user-selected Vault. Phase 12 adds the watcher that makes manual Obsidian edits searchable without a restart.

References: [Obsidian Bases syntax](https://obsidian.md/help/bases/syntax), [Create a base](https://obsidian.md/help/bases/create-base), and [Obsidian URI](https://help.obsidian.md/Extending%2BObsidian/Obsidian%2BURI).
