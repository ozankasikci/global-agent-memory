# MCP V1 capability guide

Use this reference only to choose a frozen capability. Discovery remains authoritative for exact schemas and defaults.

## Retrieve

- `memory_context`: first choice for bounded task context; pass `task` and `working_directory`.
- `memory_search`: focused lookup for exact IDs, identifiers, error strings, decisions, conventions, or solutions.
- `memory_get`: full current note before citation, update, or lifecycle work.
- `memory_tags`: browse bounded tag metadata.
- `memory_status`: daemon, index, watcher, vector, conflict, and degradation state.
- `memory_open`: return the Vault path and encoded Obsidian URI.
- `memory_dashboard_open`: issue and optionally open a short-lived authenticated local dashboard session.
- `memory_access_request`: ask the owner for a purpose-bound temporary protected-memory capability without revealing protected metadata.
- `memory_access_status`: poll a request and receive `access_grant` only after owner approval.

Useful read-only resources include `memory://v1/status`, `memory://v1/projects`, `memory://v1/candidates`, `memory://v1/recent`, `memory://v1/tags`, and the discovered note/project URI templates.

## Write and lifecycle

- `memory_remember`: create a candidate after duplicate search.
- `memory_update`: optimistic body, metadata, or section patch.
- `memory_approve`: activate a reviewed candidate.
- `memory_reject`: reject with a reason.
- `memory_supersede`: replace while preserving reciprocal history.
- `memory_archive`: archive; hard-delete only with explicit intent.
- `memory_reindex`: request generated-index reconciliation.
- `memory_projects`: list, get, detect, add, update, or deactivate project entries.

Every mutation needs a fresh unique `request_id`. Reusing the same ID is valid only for an exact replay of the same operation and payload.

## Examples

Before debugging a recurring error:

1. Call `memory_context` with the debugging task and working directory.
2. Call `memory_search` with the exact error string if the bundle lacks it.
3. If `protected_memory_may_be_relevant` is returned, request the least access required and wait for owner approval. Sealed memory is never agent-readable.
4. Call `memory_get` for the selected result, passing the approved `access_grant` when required.
5. Cite the result ID and path if it informs the fix.

After verifying a durable convention:

1. Search the convention in the detected project and applicable global scope.
2. If no applicable duplicate exists, call `memory_remember` with type `convention`, narrow scope, evidence, and a unique request ID.
3. Leave it as a candidate and report its ID/path for review.
