---
name: global-memory
description: Retrieve and curate durable, project-aware knowledge through the Global Memory MCP server. Use before substantial planning, implementation, refactoring, debugging, handoff preparation, or investigation when prior decisions, exact identifiers, recurring errors, verified solutions, preferences, or conventions may matter; also use after work when durable verified knowledge may be worth proposing as a review candidate.
---

# Global Memory

Skill version: `1.0.0`  
MCP contract version: `v1`

Use the canonical MCP capability names. Do not assume a client-specific server prefix. Read [references/contract-v1.md](references/contract-v1.md) only when exact capability selection or arguments are unclear.

## Before substantial work

1. Derive the project from the current working directory. Pass `working_directory`; add `project` only when the user supplied or confirmed it.
2. Call `memory_context` with the concrete task before broad searches. Keep `cross_project=false` unless the user explicitly requests comparison or wider scope.
3. Use `memory_search` for a prior decision, exact ID, symbol, error string, convention, or known solution that the context bundle did not answer.
4. Use `memory_get` before relying on, citing, or changing one result. Treat status and applicability labels as constraints, not decoration.
5. When memory materially informs the work, cite its memory ID and Vault-relative path in the response or handoff.

Do not turn retrieval into ceremony for trivial work. If the available context is sufficient and no durable history could change the answer, proceed.

## Keep project isolation

- Default to global, organization, and the detected current project.
- Never enable cross-project retrieval merely because results are sparse.
- If project detection is unresolved, state that fact and ask for a project only when it changes the work materially.
- Never infer project identity from note text.

## Propose durable memory

At completion, decide whether the work established durable, reusable, and verified knowledge. Save nothing when it produced only transient logs, guesses, intermediate failures, routine progress, or facts already present.

When a candidate is justified:

1. Search for duplicates in the same scope and project.
2. Prefer updating a matching memory over creating a near-duplicate.
3. Call `memory_remember` to create a candidate, not an active fact. Use the narrowest correct scope and include evidence in the body or `source_ref`.
4. Report the candidate ID and path so a person can review it.

Never store credentials, tokens, private keys, secrets, raw prompts, full transient logs, embeddings, or unrelated personal data.

## Update and lifecycle safely

1. Call `memory_get` immediately before an update or lifecycle action.
2. Pass the returned `updated_at`/version as `expected_updated_at` where supported.
3. Use `memory_update` for descriptive metadata, body, or explicit section patches. Do not rewrite immutable identity or lifecycle fields.
4. Use `memory_supersede` when newer knowledge replaces an older claim; preserve reciprocal history instead of rewriting the old note as if it had always been true.
5. Use `memory_approve`, `memory_reject`, and `memory_archive` only when the user or workflow explicitly authorizes that lifecycle decision.
6. Treat `hard_delete=true` as destructive and require explicit user intent.
7. On `VERSION_CONFLICT`, read again and re-evaluate; never blindly retry a stale mutation.

## Completion check

Before finishing substantial work:

- Confirm whether retrieved memory still applies to the implemented result.
- Cite every memory that materially affected the outcome.
- Propose only newly verified durable knowledge.
- If nothing durable was established, save nothing and continue without commentary about memory housekeeping.

## Failure behavior

- If semantic retrieval degrades, use keyword mode unless semantic-only behavior was explicitly required.
- If the daemon is unavailable, report `DAEMON_UNAVAILABLE` and the remediation; do not read generated SQLite directly.
- If a note is invalid or duplicated, surface the stable conflict and do not silently choose a copy.
- Never bypass the MCP interface by editing lifecycle metadata or generated indexes.
