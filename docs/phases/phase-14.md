# Phase 14 report — canonical shared Agent Skill

## Completed requirements

`integrations/skills/global-memory/SKILL.md` is the single source used by both planned client installers. Its trigger description covers substantial planning, implementation, refactoring, debugging, handoffs, investigations, and completion-time durable-memory review. The workflow derives project identity from working directory, calls `memory_context` before broad search, uses focused exact retrieval, reads before reliance or mutation, defaults to project isolation, and requires ID/path citations when memory materially informs work.

Write guidance saves only durable verified knowledge, searches for duplicates first, creates review candidates, keeps scopes narrow, and saves nothing for transient or already-known outcomes. Lifecycle guidance requires fresh reads and optimistic versions, preserves history through supersession, gates approval/rejection/archive on authorization, and treats hard-delete as explicitly destructive. Security rules exclude credentials, secrets, prompts, transient logs, embeddings, and unrelated personal data.

Skill version `1.0.0` is separate from MCP contract `v1`. A single concise reference maps retrieval, mutation, lifecycle, resource, request-ID, debugging, and convention examples to canonical capability names without client prefixes.

## Validation and tests

The skill was initialized with the official local skill-creator scaffold and UI metadata generator. `quick_validate.py` passes. Contract tests parse strict two-field frontmatter, require every workflow section and both version declarations, ensure all backticked `memory_*` names are members of frozen discovery, require key security/concurrency language, and reject Claude/Codex-specific wording.

Subagent forward-testing was not run because this task did not authorize subagent use. Deterministic validation and repository contract tests provide the acceptance evidence instead.

## Commands and results

- Skill validator — `Skill is valid!`
- Skill contract tests — 2 passed.
- `make check` — Ruff and strict mypy passed; 46 unit, 33 integration, 16 contract, and 9 E2E tests passed; deterministic contract regeneration passed.

## Next phase

Phases 15 and 16 install this exact canonical directory into Claude Code and Codex, register the stdio MCP proxy through guarded adapters, and verify shared-daemon behavior without editing real user settings in normal tests.
