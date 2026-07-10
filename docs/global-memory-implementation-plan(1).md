# Global Memory System — MCP-First Implementation Plan for an AI Coding Agent

## 1. Mission and product definition

Build a local-first, project-aware, durable memory system that can be shared by every supported AI coding session on one computer.

The product is the **Global Memory MCP server**. Obsidian, Markdown, SQLite, embeddings, the daemon, the CLI, and client-specific skills exist to support that MCP interface.

The system must:

1. Use an Obsidian Vault containing Markdown files as the durable, human-readable source of truth.
2. Expose a stable, versioned Model Context Protocol interface as the primary AI-facing API.
3. Work from Claude Code, Codex CLI/IDE, and future MCP-compatible clients.
4. provide tested Agent Skills that teach Claude Code and Codex when and how to use the memory tools.
5. Support keyword, metadata, and optional semantic search.
6. Separate global, organization, project, session, candidate, superseded, rejected, and archived memories.
7. Allow the user to inspect, edit, link, approve, reject, supersede, archive, and visualize memories in Obsidian.
8. Rebuild every generated database, embedding, and cache entirely from the Vault.
9. Work without a cloud account or hosted dependency.
10. Remain useful in keyword-only mode when Ollama or vector search is unavailable.
11. Be test-driven, project-isolated, recoverable, auditable, and safe for concurrent local clients.

The initial implementation targets one user on one computer. Do not build multi-user permissions, public internet hosting, cloud synchronization, a graph database, autonomous memory extraction, or arbitrary document ingestion in V1.

---

## 2. Non-negotiable design principles

### 2.1 MCP is the public agent API

All AI-client functionality must be available through MCP tools, resources, or prompts.

Do not create a separate public REST API in V1. Internal implementation details must not leak into client integrations.

The following are allowed:

- MCP over stdio for broad local-client compatibility.
- MCP over Streamable HTTP, bound to localhost, for clients that support it and for sharing one daemon.
- An internal application-service API inside the Python process.
- Administrative CLI operations for installation, service management, migrations, and diagnostics.

The following are not allowed in V1:

- A parallel custom JSON REST contract for memory operations.
- Client integrations that read SQLite directly.
- Client integrations that write Markdown directly.
- Separate Claude-specific and Codex-specific memory implementations.

### 2.2 Markdown is the durable source of truth

The Obsidian Vault is the canonical data store. SQLite, FTS rows, vector rows, job state, caches, and derived relationships must be disposable and rebuildable.

### 2.3 Skills contain workflow, not memory

The Claude Code and Codex skills must contain instructions for using the MCP server. They must not copy project memory into skill files.

### 2.4 Candidate-first AI writes

An AI client may create a memory candidate, but it must not silently approve, merge, replace, supersede, archive, reject, or hard-delete durable memory.

### 2.5 Project isolation by default

A search from one repository must not retrieve another project's memory unless the caller explicitly enables cross-project retrieval or requests a specific other project.

### 2.6 Contract before implementation

The MCP V1 contract must be specified and tested before implementing adapters. Application behavior may evolve internally, but V1 tool schemas and semantics may not change casually after the contract freeze.

---

## 3. Mandatory engineering rules for the implementing agent

1. Read this entire specification before modifying the repository.
2. Implement phases strictly in order.
3. Do not begin a new phase until every exit criterion for the current phase passes.
4. At the start of each phase, write or update tests describing the required behavior.
5. Confirm new tests fail for the expected reason before implementation.
6. Implement the smallest complete solution that satisfies the phase.
7. Run formatting, linting, static type checking, unit tests, applicable integration tests, and applicable contract tests after every phase.
8. Never weaken or delete a test merely to make the build pass.
9. Keep domain logic independent from MCP transports, SQLite, Watchdog, Obsidian, Ollama, Claude Code, and Codex.
10. Keep MCP adapters thin. They validate MCP input, call application services, and translate results and errors.
11. Keep all generated state rebuildable from Markdown.
12. Never silently merge, overwrite, delete, approve, reject, archive, or supersede a memory.
13. Use atomic file writes and optimistic concurrency controls.
14. Use stable domain error codes independent of MCP transport details.
15. Add structured logs around indexing, writes, searches, transport failures, installation, and recovery.
16. Never log note bodies, complete prompts, embeddings, secrets, bearer tokens, or client configuration contents at normal log levels.
17. Bind network listeners to localhost by default.
18. Maintain `CHANGELOG.md`, ADRs, the MCP contract documents, generated JSON schemas, and a phase-completion checklist.
19. Do not implement V2 features or unrelated improvements before V1 acceptance passes.
20. At the end of every phase, produce a report containing:
    - completed requirements;
    - files changed;
    - tests added or updated;
    - commands executed;
    - format, lint, type-check, unit, integration, contract, and E2E results;
    - known limitations;
    - next phase.
21. When a minor implementation detail is open, choose the simplest testable option consistent with the architecture and record it in an ADR.
22. Stop only when proceeding would risk data loss, violate a mandatory requirement, or require changing the frozen public contract.

---

## 4. Fixed technology choices

Use this baseline unless a demonstrated compatibility issue requires an adapter or replacement:

- Language: Python 3.12 or newer.
- Packaging: `pyproject.toml`.
- Development workflow: `uv` where available.
- Validation and configuration: Pydantic and `pydantic-settings`.
- CLI: Typer.
- MCP implementation: official MCP Python SDK.
- MCP transports:
  - stdio server/proxy;
  - Streamable HTTP bound to `127.0.0.1`.
- Durable storage: Markdown with YAML properties in an Obsidian Vault.
- Generated metadata and keyword index: SQLite with FTS5.
- Semantic vector index: adapter interface, with `sqlite-vec` as the preferred local implementation.
- Local embedding provider: Ollama embedding API behind an adapter.
- Filesystem watching: Watchdog.
- Logging: structured logging.
- Tests: Pytest, pytest-asyncio, Hypothesis where useful.
- MCP tests: an MCP client harness using the official SDK.
- Quality: Ruff and mypy.
- Platform directories: `platformdirs`.

Do not use FastAPI or expose a custom memory REST API in V1. If the MCP SDK requires an ASGI implementation internally for Streamable HTTP, keep it transport-only and do not add unrelated HTTP routes other than minimal liveness/readiness endpoints when technically necessary.

Semantic storage and embedding providers must be replaceable. Keyword-only operation is mandatory.

---

## 5. High-level architecture

```text
Claude Code ── shared Global Memory skill ─┐
                                           │ stdio MCP
Codex CLI/IDE ─ shared Global Memory skill ├──────┐
                                           │      │
Other MCP client ──────────────────────────┘      ▼
                                      global-memory-mcp
                                      thin stdio MCP proxy
                                                │
                                                │ MCP over localhost
                                                ▼
                                      global-memoryd
                                  MCP Streamable HTTP daemon
                                                │
                     ┌──────────────────────────┼──────────────────────────┐
                     ▼                          ▼                          ▼
              application/domain        Obsidian Vault             generated indexes
                  services              Markdown + YAML          SQLite FTS + vectors
                                                                         │
                                                                         ▼
                                                                   Ollama adapter
```

### 5.1 Process responsibilities

#### `global-memoryd`

- Run the authoritative local MCP server over Streamable HTTP.
- Own configuration loading and validation.
- Validate and manage the Vault.
- Own filesystem watching.
- Serialize Markdown mutations.
- Maintain SQLite FTS and optional vector indexes.
- Execute application services.
- Expose MCP tools, resources, and prompts.
- Authenticate local Streamable HTTP clients.
- Reconcile and recover generated state on startup.

#### `global-memory-mcp`

- Run as an MCP stdio server launched by clients.
- Proxy MCP discovery and calls to `global-memoryd`.
- Preserve MCP tool/resource/prompt semantics.
- Translate daemon transport failures into stable MCP errors.
- Never read or write Vault files or indexes directly.
- Start the daemon only when explicitly configured to do so; do not spawn duplicate unmanaged daemons.

#### `global-memory` CLI

The CLI has two categories of commands:

1. **Administrative commands**, which may call local application code directly when the daemon is unavailable:
   - initialize;
   - install or remove services;
   - configure;
   - migrate;
   - repair;
   - inspect generated client configuration.
2. **Runtime memory commands**, which must use the MCP client path by default:
   - search;
   - context;
   - remember;
   - approve;
   - reject;
   - update;
   - supersede;
   - archive;
   - status;
   - reindex.

This ensures the CLI exercises the same public behavior as AI clients.

### 5.2 Why one daemon plus a stdio proxy

Many local clients launch one stdio MCP process per session. The daemon prevents each session from starting its own watcher, database owner, and embedding queue. Clients that support local Streamable HTTP may connect directly; other clients use the stdio proxy.

### 5.3 Dependency direction

```text
client integrations / MCP transports / CLI
                  ↓
           application services
                  ↓
                domain
                  ↑
Vault / SQLite / vector / embedding / Git adapters
```

The domain layer must not import MCP SDK classes, SQLite drivers, Watchdog, Obsidian-specific utilities, Ollama clients, Claude Code configuration code, or Codex configuration code.

---

## 6. Filesystem layout

### 6.1 User configuration and generated state

Use `platformdirs`. Conceptually:

```text
~/.config/global-memory/config.toml
~/.config/global-memory/auth-token
~/.local/share/global-memory/memory.db
~/.local/share/global-memory/vector/
~/.local/share/global-memory/logs/
~/.local/share/global-memory/run/
```

On macOS, use the corresponding Application Support and configuration directories selected by `platformdirs`.

Do not place databases, locks, tokens, logs, or runtime files inside the Vault.

### 6.2 Repository-managed integration files

```text
global-memory/
└── integrations/
    ├── skills/
    │   └── global-memory/
    │       ├── SKILL.md
    │       └── references/
    │           └── tool-usage.md
    ├── claude-code/
    │   └── CLAUDE.md.snippet
    └── codex/
        └── AGENTS.md.snippet
```

The same physical skill directory should be installable into both clients, preferably through symlinks with a copy fallback.

### 6.3 Vault layout

```text
Global Memory/
├── 00 Inbox/
│   └── AI Candidates/
├── 10 Global/
│   ├── Preferences/
│   ├── Conventions/
│   └── Reusable Knowledge/
├── 15 Organization/
├── 20 Projects/
│   └── <Project Name>/
│       ├── Project Overview.md
│       ├── Decisions/
│       ├── Facts/
│       ├── Problems and Solutions/
│       └── Session Summaries/
├── 30 Decisions/
├── 40 Problems and Solutions/
├── 50 Entities/
│   ├── People/
│   ├── Organizations/
│   └── Technologies/
├── 70 Session Summaries/
├── 90 Archive/
├── Templates/
├── Dashboards/
└── README.md
```

The service may create missing managed directories but must never reorganize arbitrary user files without an explicit command.

---

## 7. Domain model

### 7.1 Memory types

Start with:

- `project`
- `decision`
- `fact`
- `solution`
- `preference`
- `convention`
- `session_summary`
- `entity`
- `reference`

Tool-created notes must use supported values. Parser/indexer code must preserve unknown future values as custom strings without destroying files.

### 7.2 Scopes

- `global`
- `organization`
- `project`
- `session`
- `archive`

### 7.3 Statuses

- `candidate`
- `active`
- `superseded`
- `archived`
- `rejected`

### 7.4 Required YAML properties

```yaml
---
id: "mem_<uuid>"
title: "Human-readable title"
type: decision
scope: project
project: "Eggvolution"
status: active
confidence: 0.90
importance: 0.80
created_at: 2026-07-10T10:00:00Z
updated_at: 2026-07-10T10:00:00Z
tags:
  - unity
  - persistence
links:
  - "[[Eggvolution]]"
source_kind: manual
source_ref: null
supersedes: []
superseded_by: null
---
```

### 7.5 Validation rules

1. `id`, `title`, `type`, `scope`, `status`, `created_at`, and `updated_at` are mandatory for managed notes.
2. Project-scoped notes require a project.
3. Confidence and importance must be between `0.0` and `1.0`.
4. `updated_at` cannot be earlier than `created_at`.
5. IDs are immutable.
6. File names are not identity.
7. Candidate notes created through MCP must reside under `00 Inbox/AI Candidates/`.
8. Active notes cannot have `superseded_by` unless the same atomic operation changes their status to `superseded`.
9. Unknown YAML properties must survive service updates.
10. The Markdown body must remain unchanged except for explicitly requested modifications.
11. Duplicate IDs are conflicts; the service must not silently choose one file.

### 7.6 Recommended body headings

```markdown
# Title

## Summary

## Context

## Decision or Knowledge

## Reasoning

## Alternatives Considered

## Evidence

## Consequences

## Related Memories
```

---

## 8. SQLite and generated-index schema

Use migrations from the first commit.

### 8.1 `documents`

- `id TEXT PRIMARY KEY`
- `path TEXT UNIQUE NOT NULL`
- `title TEXT NOT NULL`
- `type TEXT NOT NULL`
- `scope TEXT NOT NULL`
- `project TEXT NULL`
- `status TEXT NOT NULL`
- `confidence REAL NOT NULL`
- `importance REAL NOT NULL`
- `created_at TEXT NOT NULL`
- `updated_at TEXT NOT NULL`
- `content_hash TEXT NOT NULL`
- `metadata_json TEXT NOT NULL`
- `indexed_at TEXT NOT NULL`
- `deleted_at TEXT NULL`

### 8.2 `chunks`

- `id TEXT PRIMARY KEY`
- `document_id TEXT NOT NULL`
- `ordinal INTEGER NOT NULL`
- `heading_path TEXT NULL`
- `content TEXT NOT NULL`
- `content_hash TEXT NOT NULL`
- `estimated_tokens INTEGER NOT NULL`
- unique `(document_id, ordinal)`

### 8.3 `chunks_fts`

FTS5 indexes:

- chunk content;
- document title;
- heading path;
- normalized tags;
- project;
- type.

Maintain a reliable mapping from FTS rows to chunk IDs.

### 8.4 `links`

- `source_document_id`
- `target_reference`
- `target_document_id NULL`
- `link_kind`

### 8.5 `embeddings`

Logical fields:

- `chunk_id`
- `provider`
- `model`
- `dimension`
- `content_hash`
- vector payload through the vector adapter.

Do not regenerate an embedding when chunk hash, provider, model, and dimensions are unchanged.

### 8.6 `projects`

- stable ID;
- canonical name;
- aliases;
- local root paths;
- normalized Git remotes;
- organization;
- active flag.

### 8.7 `index_events`

Track indexing operations for diagnostics and recovery.

### 8.8 `mutation_requests`

Track idempotent mutation requests:

- `request_id TEXT PRIMARY KEY`
- `operation TEXT NOT NULL`
- `payload_hash TEXT NOT NULL`
- `result_json TEXT NOT NULL`
- `created_at TEXT NOT NULL`

A retried mutation with the same request ID and payload must return the original result. The same request ID with a different payload must return a conflict.

### 8.9 `schema_migrations`

Track database migrations.

Enable WAL mode and foreign keys. Use explicit transactions for index and lifecycle updates.

---

## 9. Indexing behavior

### 9.1 Pipeline

```text
file event or reindex request
  → validate path is inside Vault
  → ignore excluded paths and non-Markdown files
  → read stable snapshot
  → parse YAML and Markdown
  → normalize metadata
  → calculate content hash
  → skip unchanged note
  → deterministic chunking
  → transactionally upsert document, chunks, FTS, and links
  → schedule embeddings for changed chunks
  → record completion or stable failure
```

### 9.2 File safety

- Ignore temporary files, Obsidian cache files, hidden runtime files, and configured exclusions.
- Debounce rapid saves.
- Retry a file that changes while being read.
- Use atomic service writes: temporary sibling file, flush/fsync where practical, then rename.
- Refuse traversal or symlink escapes.
- Never follow a symlink outside the Vault.

### 9.3 Chunking

1. Preserve note title and heading hierarchy as context.
2. Prefer heading and paragraph boundaries.
3. Do not split inside fenced code blocks, YAML, tables, or list items unless they exceed the hard maximum.
4. Target approximately 400–700 tokens.
5. Use approximately 50 tokens of overlap when splitting long sections.
6. Store deterministic ordinals and hashes.
7. Index small notes as one chunk.
8. Use a replaceable token estimator so tests do not depend on an external tokenizer.

### 9.4 Deletes, moves, copies

- Deleting a file removes it from active search but retains a diagnostic tombstone.
- Moving a file with the same ID updates its path.
- Copying a file with an existing ID creates a duplicate-ID conflict; neither copy is silently selected as canonical.

---

## 10. Search and context behavior

### 10.1 Modes

- `keyword`
- `semantic`, only when available
- `hybrid`, default
- `metadata`

### 10.2 Default scope rules

When a project is known, default search includes:

1. active memories from that project;
2. active organization memories;
3. active global memories;
4. project session summaries with a lower ranking contribution.

It excludes:

- other projects unless `cross_project=true`;
- candidates unless requested;
- archived, rejected, and superseded notes unless requested.

When no project is known, search global and organization scopes. Never search every project silently.

### 10.3 Hybrid ranking

Implement behind a `RetrievalStrategy` interface:

1. Retrieve keyword candidates from FTS5.
2. Retrieve semantic candidates from the vector adapter.
3. Fuse rankings with Reciprocal Rank Fusion.
4. Apply bounded adjustments for exact project match, global/organization applicability, active status, importance, recency, session-summary penalty, and stale status.
5. Group chunk results by document.
6. Return one primary passage plus optional supporting passages.

Tests should assert ordering, filtering, and explanation fields—not exact floating-point values.

### 10.4 Search result fields

Every result must include:

- memory ID;
- title;
- relative Vault path;
- type;
- scope;
- project;
- status;
- matched excerpt;
- matched heading;
- final score;
- keyword rank when present;
- semantic rank when present;
- reasons for inclusion;
- updated timestamp;
- Obsidian URI when possible.

### 10.5 Pagination

Search tools returning collections must support cursor pagination:

- `limit`, with a documented maximum;
- `cursor`, opaque to clients;
- `next_cursor`, nullable;
- deterministic ordering for the same index snapshot.

Do not use offset pagination for large result sets.

### 10.6 Context packing

`memory_context` must:

1. apply normal scope rules;
2. prioritize diversity across relevant note types;
3. avoid duplicate chunks;
4. fit within the requested token budget;
5. attach source IDs and paths;
6. label candidate, archived, superseded, rejected, and cross-project content;
7. treat stored note text as untrusted data, never as instructions to the memory service;
8. return structured JSON plus concise rendered text.

---

## 11. Lifecycle behavior

### 11.1 Candidate-first writes

All memories created through MCP must default to candidate status. MCP must not expose an argument that lets an AI client directly create an active note in V1.

Manual administrative CLI import may create active notes only with an explicit user flag.

### 11.2 Duplicate detection

Before candidate creation:

1. compare normalized exact content hashes;
2. find close title/body matches in the same applicable scope;
3. return possible duplicates with IDs and excerpts;
4. require `force=true` to create a likely duplicate;
5. never auto-merge.

### 11.3 Approval and rejection

`memory_approve` must validate, activate, route, move, preserve identity, update timestamps, trigger indexing, and return the final path.

`memory_reject` must mark the candidate rejected and move it to a deterministic rejected/archive location. It must preserve the note for audit unless the user separately requests hard deletion.

### 11.4 Updates

- Require `expected_updated_at` or an equivalent version token.
- Reject stale writes with `VERSION_CONFLICT`.
- Preserve unknown YAML properties.
- Support metadata patches and explicit body/section replacement.
- Record an audit event.

### 11.5 Superseding

Create or identify the replacement, mark the old note superseded, set reciprocal references, and preserve both notes.

### 11.6 Archive and hard delete

- `memory_archive` changes status and moves the note under `90 Archive/`.
- `memory_forget` is an alias for archive by default.
- Hard deletion requires explicit user intent, a separate argument or command, and a tombstone.

### 11.7 Idempotency

All mutation tools require or accept a client-generated `request_id`. Safe retries must not create duplicate notes or repeat lifecycle transitions.

---

## 12. Project detection

Resolve project scope in this order:

1. explicit `project` input;
2. configured mapping for `working_directory`;
3. nearest Git root;
4. normalized Git remote mapping;
5. directory alias;
6. no project.

Never infer a project solely from natural-language query text.

Example configuration:

```toml
[[projects]]
name = "Eggvolution"
aliases = ["eggvolution", "egg-evolution"]
roots = ["/Users/ozan/Projects/eggvolution"]
git_remotes = ["git@github.com:longhorn-games/eggvolution.git"]
organization = "Longhorn Games"
```

Provide project management through MCP and CLI:

- list;
- get;
- add;
- update;
- remove/deactivate;
- detect from path.

Normalize SSH and HTTPS forms of the same Git remote.

---

## 13. MCP V1 contract

The MCP contract is the primary external specification.

### 13.1 Versioning policy

- Tool names in V1 use stable readable names such as `memory_search`.
- Every tool response includes `contract_version: 1`.
- The server advertises product version and contract version through `memory_status` and `memory://v1/status`.
- Additive optional fields are allowed within V1.
- Removing fields, changing meanings, changing defaults, or making optional fields mandatory requires a new major contract.
- A future breaking version uses parallel tool names such as `memory_v2_search` rather than silently changing V1 behavior.
- Generated JSON schemas for V1 are committed under `contracts/mcp/v1/` and compared in CI.

### 13.2 Common request fields

Where applicable:

- `project?: string`
- `working_directory?: string`
- `request_id?: string` for mutations
- `verbose?: boolean = false`

### 13.3 Common success envelope

```json
{
  "contract_version": 1,
  "ok": true,
  "data": {},
  "warnings": [],
  "diagnostics": null
}
```

### 13.4 Common error envelope

```json
{
  "contract_version": 1,
  "ok": false,
  "error": {
    "code": "VERSION_CONFLICT",
    "message": "The memory changed after it was read.",
    "retryable": false,
    "details": {},
    "remediation": "Read the memory again and apply the update to the latest version."
  }
}
```

Use MCP-native error signaling while preserving this structured payload when supported.

### 13.5 Mandatory MCP tools

#### `memory_search`

Inputs:

- `query: string`
- `project?: string`
- `working_directory?: string`
- `scopes?: string[]`
- `types?: string[]`
- `tags?: string[]`
- `statuses?: string[]`
- `cross_project?: boolean = false`
- `include_candidates?: boolean = false`
- `include_archived?: boolean = false`
- `include_rejected?: boolean = false`
- `include_superseded?: boolean = false`
- `mode?: "hybrid" | "keyword" | "semantic" | "metadata" = "hybrid"`
- `limit?: integer = 10`
- `cursor?: string`

#### `memory_context`

Inputs:

- `task: string`
- `project?: string`
- `working_directory?: string`
- `token_budget?: integer = 3000`
- `cross_project?: boolean = false`
- `types?: string[]`
- `tags?: string[]`

#### `memory_get`

Inputs:

- `id: string`

Returns metadata, body, path, links, lifecycle status, source details, and concurrency version.

#### `memory_remember`

Inputs:

- `request_id: string`
- `title: string`
- `content: string`
- `type: string`
- `scope: string`
- `project?: string`
- `tags?: string[]`
- `links?: string[]`
- `source_kind?: string`
- `source_ref?: string`
- `confidence?: number`
- `importance?: number`
- `force?: boolean = false`

Always creates a candidate in V1.

#### `memory_update`

Inputs:

- `request_id: string`
- `id: string`
- `expected_updated_at: string`
- `metadata_patch?: object`
- `body?: string`
- `section_patch?: object`

#### `memory_approve`

Inputs:

- `request_id: string`
- `id: string`
- `expected_updated_at?: string`
- `destination_override?: string`

#### `memory_reject`

Inputs:

- `request_id: string`
- `id: string`
- `reason: string`
- `expected_updated_at?: string`

#### `memory_supersede`

Inputs:

- `request_id: string`
- `old_id: string`
- `replacement_id?: string`
- `replacement?: object`
- `reason: string`
- exactly one of `replacement_id` or `replacement`.

#### `memory_archive`

Inputs:

- `request_id: string`
- `id: string`
- `reason: string`
- `hard_delete?: boolean = false`

#### `memory_status`

Returns:

- daemon and package versions;
- MCP contract version;
- Vault path and validity;
- document/chunk counts;
- pending indexing and embedding jobs;
- watcher state;
- embedding/vector state;
- duplicate-ID conflicts;
- invalid-note count;
- last indexing error;
- keyword-only fallback state;
- connected transport mode.

#### `memory_reindex`

Inputs:

- `request_id: string`
- `full?: boolean = false`
- `paths?: string[]`

Paths must be relative to the configured Vault and validated.

#### `memory_open`

Inputs:

- `id: string`

Returns filesystem path and Obsidian URI. It must not launch an external application automatically.

#### `memory_projects`

Inputs:

- `action: "list" | "get" | "detect" | "add" | "update" | "deactivate"`
- action-specific payload.

Mutating actions require `request_id`.

#### `memory_tags`

Inputs:

- optional project, scope, status, prefix, limit, and cursor filters.

Returns normalized tags and usage counts.

### 13.6 Mandatory MCP resources

Expose read-only resources:

- `memory://v1/status`
- `memory://v1/projects`
- `memory://v1/project/{project}`
- `memory://v1/project/{project}/recent`
- `memory://v1/project/{project}/decisions`
- `memory://v1/project/{project}/open-problems`
- `memory://v1/note/{id}`
- `memory://v1/candidates`
- `memory://v1/recent`
- `memory://v1/tags`

Resources must enforce the same scope and status semantics as tools. Do not expose the SQLite file, vector data, auth token, or raw runtime logs.

### 13.7 Mandatory MCP prompts

Expose reusable prompts that reference MCP tools/resources rather than embedding memory:

- `prepare_project_context`
- `summarize_project_state`
- `review_recent_decisions`
- `investigate_previous_bug`
- `prepare_implementation_handoff`
- `review_memory_candidates`

Each prompt must:

- accept explicit arguments;
- describe when to search versus read a resource;
- preserve project isolation;
- require source IDs/paths in generated output;
- avoid automatically writing memory;
- remain client-neutral.

### 13.8 Capability discovery

Discovery tests must verify tools, resources, prompts, JSON schemas, descriptions, defaults, and contract version. Descriptions must be precise enough for automatic tool selection by an AI client.

---

## 14. MCP transports and local security

### 14.1 Streamable HTTP daemon

- Bind to `127.0.0.1` by default.
- Use a configurable port.
- Require a generated local bearer token.
- Store the token with user-only permissions.
- Validate host/origin as supported by the SDK.
- Apply request-size and connection limits.
- Expose only MCP transport endpoints plus minimal liveness/readiness endpoints if technically required.
- Do not expose OpenAPI or a generic REST surface.

### 14.2 Stdio proxy

- Read daemon endpoint and token from protected configuration.
- Proxy discovery, tools, resources, prompts, cancellation, and errors.
- Preserve request IDs and structured errors.
- Fail quickly with `DAEMON_UNAVAILABLE` and remediation instructions.
- Terminate cleanly when stdin closes.
- Never echo logs to stdout; protocol output only. Logs go to stderr.

### 14.3 Direct stdio fallback

For development and recovery, optionally support a single-process direct stdio mode. It must use the same MCP contract and application services. It must not be the default when the shared daemon is installed.

---

## 15. Obsidian integration

### 15.1 Templates

Create templates for:

- Project Overview
- Decision
- Fact
- Problem and Solution
- Preference
- Convention
- Session Summary
- Entity

### 15.2 Dashboards and Bases

Create views for:

1. AI candidates awaiting review.
2. Active decisions grouped by project.
3. Problems and verified solutions.
4. Recently updated memories.
5. Superseded memories.
6. Rejected candidates.
7. Archived memories.
8. Low-confidence memories.
9. Unresolved links.
10. Duplicate-ID or validation conflicts, when representable safely.

### 15.3 Graph behavior

- Project-scoped notes link to their project note.
- Superseded notes link reciprocally.
- Decisions link to supplied technologies and related decisions.
- Session summaries link only to explicitly referenced memories.
- Do not invent semantic links in V1.

### 15.4 Obsidian URI

Return:

```text
obsidian://open?vault=<encoded-vault-name>&file=<encoded-relative-path>
```

Test URI generation without requiring Obsidian in CI.

---

## 16. Claude Code and Codex skills

### 16.1 Shared skill source

Maintain one canonical Agent Skill:

```text
integrations/skills/global-memory/SKILL.md
```

The skill must teach the agent to:

- retrieve context before substantial planning, implementation, refactoring, or debugging;
- derive the project from the working directory;
- use `memory_context` before broad searches;
- use `memory_search` for previous decisions, exact identifiers, recurring errors, and prior solutions;
- avoid cross-project search by default;
- create candidates only for durable, verified knowledge;
- search for duplicates before remembering;
- never store credentials or transient logs;
- read before update;
- use optimistic concurrency;
- use supersede rather than rewriting history;
- save nothing when no durable knowledge was established;
- cite memory IDs and Vault paths when memory materially informs an answer.

The skill must not assume client-specific tool prefixes. It should refer to the server and canonical tool names.

### 16.2 Claude Code installation target

Install or symlink into:

```text
~/.claude/skills/global-memory
```

Optionally append a clearly delimited managed snippet to `~/.claude/CLAUDE.md` only with explicit user consent or an installation flag. Never overwrite unrelated content.

Register the MCP server at user scope using Claude Code's supported configuration mechanism. Prefer invoking the installed CLI when available; otherwise make a guarded, backed-up configuration edit through an adapter.

### 16.3 Codex installation target

Install or symlink into:

```text
~/.agents/skills/global-memory
```

Optionally append a clearly delimited managed snippet to `~/.codex/AGENTS.md` only with explicit consent or an installation flag.

Register the MCP server in Codex's user configuration through the supported CLI or a guarded, backed-up configuration adapter.

### 16.4 Installation commands

Implement:

```text
global-memory integrations install claude-code
global-memory integrations install codex
global-memory integrations install all
global-memory integrations status
global-memory integrations verify claude-code
global-memory integrations verify codex
global-memory integrations verify all
global-memory integrations uninstall claude-code
global-memory integrations uninstall codex
global-memory integrations uninstall all
```

Options should include:

- `--copy` instead of symlink;
- `--with-global-instructions`;
- `--dry-run`;
- `--json`;
- `--force` only for replacing artifacts previously managed by this product.

### 16.5 Installer safety

- Detect existing unmanaged skill directories and refuse replacement without explicit action.
- Back up any client config before editing it.
- Use managed start/end markers for instruction snippets.
- Preserve unrelated client configuration byte-for-byte where practical.
- Make install/uninstall idempotent.
- Never remove files not recorded in the integration manifest.
- Store an integration manifest containing installed paths, installation mode, hashes, and backup locations.

### 16.6 Verification behavior

`integrations verify` must check:

1. client executable availability when applicable;
2. skill path and content hash;
3. MCP registration;
4. daemon readiness;
5. tool/resource/prompt discovery;
6. `memory_status` call;
7. temporary candidate create/read/reject or archive flow, with cleanup;
8. project detection from a temporary Git repository;
9. no cross-project leakage in the smoke fixture.

When the real client executable is unavailable in CI, use adapter and configuration tests. On a target machine with the client installed, run a live verification and record the result.

---

## 17. Configuration

Example `config.toml`:

```toml
vault_path = "/Users/example/Documents/Global Memory"
log_level = "INFO"

[mcp]
host = "127.0.0.1"
port = 8765
transport = "streamable-http"
require_local_token = true
max_request_bytes = 1048576

[index]
watch = true
debounce_ms = 500
excluded_globs = [".obsidian/**", ".trash/**"]
chunk_target_tokens = 550
chunk_overlap_tokens = 50

[search]
default_mode = "hybrid"
keyword_candidates = 50
semantic_candidates = 50
rrf_k = 60
max_results = 100

[embeddings]
enabled = true
provider = "ollama"
base_url = "http://127.0.0.1:11434"
model = "<configured embedding model>"
batch_size = 32

[integrations]
prefer_symlinks = true
manage_global_instructions = false
```

Rules:

- environment variables override the file;
- CLI arguments override environment variables;
- secrets never belong in the Vault;
- configuration validation must explain every invalid field;
- embedding configuration changes mark affected chunks for re-embedding;
- client integration paths must be resolved through platform-aware adapters and explicit configuration, not scattered constants.

---

## 18. Stable error model

Define transport-independent error codes:

- `CONTRACT_VERSION_UNSUPPORTED`
- `CONFIG_INVALID`
- `VAULT_NOT_FOUND`
- `VAULT_NOT_WRITABLE`
- `NOTE_NOT_FOUND`
- `NOTE_INVALID`
- `DUPLICATE_ID`
- `POSSIBLE_DUPLICATE`
- `REQUEST_ID_CONFLICT`
- `VERSION_CONFLICT`
- `PATH_OUTSIDE_VAULT`
- `PROJECT_NOT_FOUND`
- `EMBEDDING_PROVIDER_UNAVAILABLE`
- `VECTOR_INDEX_UNAVAILABLE`
- `INDEX_CORRUPT`
- `INDEX_BUSY`
- `DAEMON_UNAVAILABLE`
- `UNAUTHORIZED`
- `REQUEST_TOO_LARGE`
- `CLIENT_NOT_INSTALLED`
- `INTEGRATION_CONFLICT`
- `INTEGRATION_VERIFY_FAILED`
- `INTERNAL_ERROR`

Every error must contain:

- code;
- human-readable message;
- retryable flag;
- safe details;
- remediation when useful.

Semantic failures fall back to keyword search unless semantic-only mode was explicitly requested.

---

## 19. Observability and diagnostics

### 19.1 Structured logs

Log:

- startup/shutdown;
- MCP transport startup and client connection counts;
- contract version;
- configuration validation;
- watcher state;
- index operation IDs and relative paths;
- counts and elapsed time;
- search mode, filters, candidate counts, fallback state, and elapsed time;
- lifecycle event IDs;
- integration install/verify/uninstall events;
- stable error codes.

Do not log content, embeddings, prompts, auth tokens, or entire client configuration files.

### 19.2 Doctor command

`global-memory doctor` must check:

- configuration;
- Vault existence and permissions;
- managed folders;
- SQLite migrations, WAL, integrity, and FTS5;
- vector adapter;
- Ollama connectivity and model;
- duplicate IDs;
- invalid frontmatter;
- unresolved projects;
- stale jobs;
- daemon readiness;
- direct MCP discovery;
- stdio proxy connectivity;
- MCP contract schema hashes;
- Claude Code integration state;
- Codex integration state.

Support human-readable and `--json` output.

---

## 20. Test strategy

### 20.1 General rules

- Use temporary Vaults, databases, home directories, Git repositories, and client configuration trees.
- Normal tests must not depend on Obsidian, Ollama, internet access, or real user configuration.
- Implement deterministic fake embedding and vector adapters.
- Freeze time in lifecycle tests.
- Normalize platform-dependent paths.
- Never invoke or modify the user's actual Claude Code or Codex settings in tests.

### 20.2 Contract tests written first

Before backend implementation, commit:

- tool input/output JSON schemas;
- resource URI templates and response schemas;
- prompt definitions and argument schemas;
- common success/error envelopes;
- golden discovery snapshot;
- version compatibility rules;
- example valid and invalid calls.

Contract tests must fail until the implementation satisfies them.

### 20.3 Unit tests

Cover:

- domain validation;
- unknown frontmatter preservation;
- Markdown round trips;
- path safety and symlink rejection;
- canonical routing;
- content hashing;
- deterministic chunking;
- RRF invariants;
- scope filtering;
- project detection;
- Git remote normalization;
- Obsidian URI encoding;
- lifecycle transitions;
- optimistic concurrency;
- mutation idempotency;
- error translation;
- MCP schema generation;
- integration-manifest behavior;
- managed-snippet insertion/removal;
- client config preservation.

### 20.4 Property-based tests

Use Hypothesis for:

- frontmatter parse/write round trips;
- Unicode titles, tags, projects, paths, and links;
- Markdown with headings, tables, lists, and code fences;
- traversal and symlink-like path inputs;
- rank-fusion invariants;
- configuration precedence;
- cursor encoding/decoding;
- request ID idempotency;
- managed config edits preserving unrelated content.

### 20.5 Integration tests

Cover:

- Vault initialization;
- full and incremental indexing;
- create/edit/move/delete;
- FTS, semantic, and hybrid search;
- complete database rebuild;
- duplicate IDs;
- candidate, approve, reject, archive, supersede flows;
- concurrent reads and conflicting writes;
- daemon restart with pending work;
- keyword-only fallback;
- MCP Streamable HTTP server;
- stdio proxy to daemon;
- CLI using MCP for runtime operations;
- fake Claude Code and Codex home installations.

### 20.6 MCP contract tests

Verify:

- tool, resource, and prompt discovery;
- exact V1 names;
- valid schemas and defaults;
- common envelopes;
- cursor pagination;
- every mandatory tool;
- every mandatory resource;
- every mandatory prompt;
- structured errors;
- cancellation and clean termination where supported;
- daemon-unavailable behavior;
- idempotent mutations;
- project isolation;
- no writes outside the Vault;
- golden contract snapshot stability.

Any intended contract change requires an explicit contract-change ADR and compatibility review.

### 20.7 End-to-end tests

Start a real daemon with a temporary Vault and invoke it through the stdio proxy.

Mandatory flows:

1. Manually create a project note, index it, and find it through MCP.
2. Create a candidate through MCP, verify the Markdown file, approve it, and find it as active.
3. Reject a candidate and verify default search excludes it.
4. Edit a note as Obsidian would and verify search reflects the change.
5. Search from two working directories and verify project isolation.
6. Stop semantic services and verify hybrid fallback.
7. Delete generated state and rebuild equivalent search-visible memory.
8. Attempt stale update and receive `VERSION_CONFLICT` without loss.
9. Retry a mutation with the same `request_id` and receive the original result.
10. Reuse the request ID with a different payload and receive `REQUEST_ID_CONFLICT`.
11. Attempt traversal and receive `PATH_OUTSIDE_VAULT`.
12. Discover prompts/resources/tools from two independent MCP clients sharing one daemon.
13. Install both skills into a fake home, verify, uninstall, and restore prior config.
14. Run CLI search and confirm it traverses the MCP path rather than accessing SQLite directly.

### 20.8 Live client acceptance tests

These are target-machine release tests, not normal CI:

#### Claude Code

- install integration;
- confirm skill appears;
- confirm MCP server appears at user scope;
- invoke the skill explicitly;
- retrieve project context;
- create a candidate with user approval;
- verify the candidate in Obsidian;
- uninstall and confirm unrelated settings remain.

#### Codex CLI/IDE

- install integration;
- confirm skill appears;
- confirm MCP server discovery;
- invoke the skill explicitly;
- retrieve the same shared memory;
- create or read a candidate;
- uninstall and confirm unrelated settings remain.

Record command outputs, client versions, and pass/fail results in the release checklist without storing secrets.

### 20.9 Performance tests

Generate at least 10,000 notes and record:

- full keyword index time;
- incremental update latency;
- FTS P50/P95;
- hybrid P50/P95 with fake embeddings;
- MCP request overhead through Streamable HTTP;
- MCP request overhead through stdio proxy;
- memory usage;
- database size.

Initial regression targets on a modern laptop:

- changed note searchable within 3 seconds;
- warm FTS P95 under 150 ms for 10,000 notes;
- warm hybrid P95 under 750 ms excluding model cold start;
- stdio proxy overhead under 100 ms P95 beyond daemon execution time;
- no full reindex for one-file changes.

### 20.10 CI matrix

Mandatory:

- Linux;
- macOS;
- baseline Python;
- latest supported Python.

Normal CI uses fake embeddings and fake client homes. Optional/manual jobs may use Ollama and installed real clients.

---

## 21. Step-by-step implementation phases

## Phase 0 — Freeze the MCP V1 contract

### Goal

Define the product interface before implementing storage or transports.

### Work

- Create `contracts/mcp/v1/`.
- Define all tool names, descriptions, input schemas, output schemas, defaults, pagination, idempotency, and examples.
- Define all resource URI templates and response schemas.
- Define all prompt names, descriptions, arguments, and generated-message templates.
- Define common success/error envelopes.
- Define error-code mapping.
- Define contract versioning and compatibility rules.
- Create a golden discovery snapshot.
- Write `docs/mcp-contract-v1.md`.
- Add ADR: MCP is the only public AI API in V1.
- Add ADR: no custom REST API in V1.

### Tests

- JSON schemas validate examples.
- Invalid examples fail for the documented reason.
- Every required tool/resource/prompt is represented.
- Duplicate names and ambiguous schemas fail.
- Golden snapshot test exists and initially fails against the missing server.

### Exit criteria

The V1 contract is reviewed, internally consistent, committed, and marked frozen. Later breaking changes require a new contract version.

---

## Phase 1 — Repository and quality gates

### Goal

Create a clean, runnable repository with enforced checks.

### Work

- Initialize `pyproject.toml` and `src/` layout.
- Add Pytest, Ruff, mypy, coverage, pre-commit, and CI.
- Add commands for format, lint, typecheck, unit, integration, contract, E2E, and full check.
- Add `README.md`, `CHANGELOG.md`, `SECURITY.md`, `CONTRIBUTING.md`, ADR directory, and phase checklist.
- Add version-only CLI and package imports.

### Tests

- Package imports.
- CLI `--version`.
- Contract files load.
- Quality commands run in CI.

### Exit criteria

A clean checkout installs and passes the baseline check command.

---

## Phase 2 — Configuration, platform paths, and Vault initialization

### Goal

Create validated configuration and a safe Vault skeleton.

### Work

- Implement configuration precedence.
- Implement platform directories.
- Implement `global-memory init`.
- Create managed Vault folders, templates directory, README, config, and local token.
- Implement config show/validate.
- Make initialization idempotent.

### Tests

- precedence;
- repeat initialization;
- no overwrite without explicit force;
- token permissions;
- stable errors for invalid paths;
- no generated database inside Vault.

### Exit criteria

A user can safely initialize twice with deterministic configuration.

---

## Phase 3 — Domain model and Markdown repository

### Goal

Implement all note behavior without SQLite or MCP transports.

### Work

- Domain models and lifecycle rules.
- Frontmatter parser/writer.
- Unknown-property preservation.
- Canonical folder routing.
- Atomic writes.
- Optimistic concurrency.
- Path safety.
- Audit events.

### Tests

- complete unit/property tests;
- Unicode and complex Markdown round trips;
- atomic-write failure preserves original;
- stale updates fail;
- symlink/traversal attacks fail.

### Exit criteria

Lifecycle operations work correctly through application interfaces with no generated index.

---

## Phase 4 — SQLite migrations, chunking, and FTS

### Goal

Build the rebuildable keyword index.

### Work

- Migration framework and schemas.
- WAL and integrity settings.
- Deterministic chunking.
- Full/per-file indexing.
- Move/delete handling.
- Keyword and metadata search.
- Rebuild and integrity checks.

### Tests

- migrations;
- full/incremental indexing;
- move preserves identity;
- delete behavior;
- rebuild equivalence;
- exact IDs, phrases, Unicode, filters;
- duplicate-ID conflicts.

### Exit criteria

Keyword search is production-usable and fully rebuildable.

---

## Phase 5 — Lifecycle application service and idempotency

### Goal

Expose transport-independent candidate, approval, rejection, update, supersede, archive, and project-safe mutation behavior.

### Work

- Candidate-first remember.
- Duplicate detection.
- Approval/rejection routing.
- Patch updates.
- Reciprocal supersede.
- Archive/hard-delete separation.
- Mutation request idempotency.

### Tests

- candidate metadata/path;
- duplicate refusal and force;
- approval/rejection;
- atomic supersede;
- archive filtering;
- stale update conflict;
- identical retry returns prior result;
- different payload with same request ID conflicts.

### Exit criteria

All lifecycle operations work through application services and are safe to retry.

---

## Phase 6 — Project registry and detection

### Goal

Resolve project scope consistently.

### Work

- Registry and aliases.
- Path/Git detection.
- Remote normalization.
- Application operations for list/get/add/update/deactivate/detect.
- Search explanations include project resolution.

### Tests

- priority order;
- nested directories;
- aliases;
- SSH/HTTPS equivalence;
- unknown path gives no project;
- explicit project wins.

### Exit criteria

Two repositories produce isolated default results.

---

## Phase 7 — Embedding and vector adapters

### Goal

Add optional semantic retrieval without creating a hard dependency.

### Work

- Provider protocols.
- Fake adapters.
- Ollama adapter with batching, timeouts, retries.
- Preferred vector adapter.
- Hash/model invalidation.
- Pending/retry jobs.
- Keyword-only fallback.

### Tests

- changed-only embedding;
- model invalidation;
- provider outage;
- semantic-only error;
- hybrid fallback labeling.

### Exit criteria

Semantic search is optional and safely degradable.

---

## Phase 8 — Hybrid retrieval, pagination, and context packing

### Goal

Return scoped, explainable, token-budgeted results.

### Work

- Retrieval interfaces.
- FTS/vector candidates.
- RRF and bounded adjustments.
- grouping/excerpts.
- default scope rules.
- cursor pagination.
- context packing.

### Tests

- exact and paraphrase ranking;
- hybrid behavior;
- project isolation;
- status flags;
- deterministic cursors;
- token budget;
- source labels and explanations.

### Exit criteria

Search semantics satisfy the frozen MCP contract before transport implementation.

---

## Phase 9 — MCP application adapter and direct test server

### Goal

Implement the complete frozen MCP V1 contract against application services.

### Work

- MCP server adapter.
- All tools.
- All resources.
- All prompts.
- Common envelopes.
- Domain-to-MCP error translation.
- Capability discovery metadata.
- Direct in-process test transport.

### Tests

- golden discovery snapshot;
- every tool/resource/prompt;
- exact schemas/defaults;
- pagination;
- idempotency;
- error envelopes;
- project isolation;
- no outside-Vault writes.

### Exit criteria

The complete V1 contract passes using the official MCP client harness in-process.

---

## Phase 10 — Shared daemon and stdio MCP proxy

### Goal

Allow multiple independent clients to share one memory service.

### Work

- `global-memoryd` Streamable HTTP MCP server.
- localhost authentication.
- liveness/readiness only if required.
- `global-memory-mcp` stdio proxy.
- cancellation/error preservation.
- daemon start/stop/status.
- degraded startup without semantic provider.

### Tests

- Streamable HTTP discovery/calls;
- token authentication;
- request limits;
- stdio discovery/calls;
- daemon unavailable;
- clean process termination;
- two proxies sharing state;
- stdout protocol purity;
- CLI runtime calls through MCP.

### Exit criteria

Two independent MCP clients can share the daemon and receive the same state.

---

## Phase 11 — Obsidian templates, dashboards, and visual workflow

### Goal

Make memory review and navigation usable in Obsidian.

### Work

- All templates.
- Bases/dashboards.
- Project overview links.
- Obsidian URIs.
- Vault README.
- Candidate approve/reject review documentation.

### Tests

- generated YAML/Markdown;
- property references;
- URI encoding;
- move/link preservation.

### Manual acceptance

- properties render;
- candidate/decision views populate;
- graph/local graph links are meaningful;
- Obsidian edits become searchable.

### Exit criteria

The user can inspect and manage memory visually without touching SQLite.

---

## Phase 12 — Watcher, jobs, resilience, and recovery

### Goal

Keep indexes current and recover from crashes.

### Work

- Watchdog/debounce.
- persisted jobs.
- bounded retries.
- startup reconciliation.
- invalid-note and duplicate-ID reporting.
- integrity recovery.
- graceful signals.

### Tests

- rapid saves;
- crash after file write;
- crash during embedding;
- invalid note isolation;
- duplicate conflicts;
- database deletion and rebuild.

### Exit criteria

Normal crashes and provider outages do not lose Markdown data.

---

## Phase 13 — CLI, packaging, service management, and doctor

### Goal

Make installation and operation straightforward while keeping runtime memory operations on MCP.

### Work

Implement:

- `init`
- `serve`
- `status`
- `doctor`
- `search`
- `context`
- `remember`
- `get`
- `approve`
- `reject`
- `update`
- `supersede`
- `archive`
- `reindex`
- `project ...`
- `config ...`
- `mcp ...`
- `integrations ...`

Add macOS `launchd`, optional Linux `systemd --user`, shell completion, backup/restore, upgrade/rollback, and package entry points.

### Tests

- subprocess CLI;
- service files;
- start/stop/status;
- fresh install;
- upgrade fixture;
- runtime commands confirmed to use MCP.

### Exit criteria

A user can initialize, start, diagnose, stop, and upgrade from documented commands.

---

## Phase 14 — Shared Agent Skill

### Goal

Create one high-quality reusable skill for both Claude Code and Codex.

### Work

- Implement canonical `SKILL.md`.
- Add concise reference material only when useful.
- Include trigger description, before-work retrieval, search, write, update, lifecycle, completion, and security rules.
- Add client-neutral examples.
- Validate that the skill names only frozen MCP V1 capabilities.
- Add skill-version metadata separate from MCP contract version.

### Tests

- frontmatter/schema lint;
- required instruction sections;
- no secrets or machine-specific paths;
- every named tool exists in contract;
- no unsupported behavior;
- snapshot test;
- prompt-evaluation fixture demonstrating correct tool-selection expectations.

### Exit criteria

One canonical skill is ready to install in both clients.

---

## Phase 15 — Claude Code integration

### Goal

Install, register, verify, and uninstall Global Memory for Claude Code safely.

### Work

- Claude Code integration adapter.
- skill symlink/copy installation.
- user-scoped MCP registration.
- optional managed global-instruction snippet.
- manifest and backups.
- status/verify/uninstall.
- documentation and examples.

### Tests

- fake-home install/uninstall;
- idempotency;
- unmanaged conflict refusal;
- config preservation;
- snippet markers;
- MCP registration adapter;
- verify flow with fake client adapter.

### Live acceptance

Run on a machine with Claude Code installed and complete the live client checklist.

### Exit criteria

Claude Code can explicitly invoke the skill and access the shared daemon without manual file editing.

---

## Phase 16 — Codex integration

### Goal

Install, register, verify, and uninstall Global Memory for Codex safely.

### Work

- Codex integration adapter.
- skill symlink/copy installation.
- MCP registration.
- optional managed `AGENTS.md` snippet.
- manifest and backups.
- status/verify/uninstall.
- documentation and examples.

### Tests

- fake-home install/uninstall;
- idempotency;
- unmanaged conflict refusal;
- config preservation;
- snippet markers;
- MCP registration adapter;
- verify flow with fake client adapter.

### Live acceptance

Run on a machine with Codex installed and complete the live client checklist.

### Exit criteria

Codex can explicitly invoke the same skill and access the same shared daemon.

---

## Phase 17 — Security, privacy, and performance hardening

### Goal

Complete the release hardening pass.

### Work

- Threat-model local MCP clients, localhost transport, malicious notes, path traversal, symlinks, oversized messages, accidental LAN exposure, prompt injection, secrets, and client config modification.
- Confirm localhost binding/token behavior.
- Treat note content as untrusted data.
- Add limits and redaction.
- Benchmark FTS, hybrid retrieval, daemon MCP, and stdio proxy.
- Document residual risks.

### Tests

- traversal/symlink corpus;
- malicious frontmatter;
- prompt-injection notes remain inert;
- oversized request rejection;
- unauthorized MCP transport;
- log capture;
- performance regression suite.

### Exit criteria

Security checklist passes and performance budgets have no unexplained regression.

---

## Phase 18 — Final V1 acceptance and release

### Goal

Prove the system works as one MCP-first product.

### Required scenarios

1. **Cross-client shared memory**
   - Create a candidate from Claude Code.
   - Review/approve it.
   - Retrieve it from Codex.

2. **Project isolation**
   - Create similar memories in two repositories.
   - Confirm default retrieval remains project-specific.

3. **Obsidian round trip**
   - Create through MCP, edit in Obsidian, approve, retrieve edited content through both clients.

4. **Exact and semantic retrieval**
   - Exact error-code search and paraphrased-concept search both succeed.

5. **Offline degradation**
   - Stop Ollama; keyword and lifecycle operations continue.

6. **Rebuildability**
   - Delete generated indexes; rebuild equivalent visible memory from Markdown.

7. **Concurrency and idempotency**
   - Conflicting updates produce one success and one version conflict.
   - Retried mutation produces no duplicate.

8. **Recovery**
   - Terminate daemon during queued work; restart and reconcile.

9. **MCP contract**
   - Golden discovery snapshot matches.
   - Tools, resources, and prompts work through Streamable HTTP and stdio.

10. **Skills**
    - Both clients discover the same skill instructions.
    - Explicit invocation works.
    - The agent retrieves before substantial work and creates only candidates.

11. **Visualization**
    - Graph and Bases show expected relationships and review queues.

12. **Security**
    - LAN binding disabled.
    - Unauthorized connection fails.
    - outside-Vault write fails.
    - integrations uninstall without damaging unrelated configuration.

### Release gates

- All mandatory Linux/macOS tests pass.
- Live Claude Code and Codex verification pass on the release machine.
- No critical or high-severity known bug.
- Domain/application coverage target at least 85%.
- Contract snapshot is frozen and tagged.
- `doctor` passes.
- Clean installation, upgrade, verification, and uninstall docs are validated.
- Release checklist and client versions are recorded.
- Tag V1 only after all gates pass.

---

## 22. V1 non-goals

Do not include:

- custom public REST memory API;
- automatic extraction from every conversation;
- autonomous memory approval or merging;
- cloud-hosted storage;
- multi-user permissions;
- public remote MCP hosting;
- mobile synchronization owned by this service;
- graph database;
- automatic semantic links;
- browser extension;
- arbitrary binary-document ingestion;
- whole source-code repository indexing;
- background generative summarization;
- encryption implemented from scratch;
- ChatGPT web integration requiring a public remote connector.

Design internal adapters so later features do not require unnecessary MCP contract changes.

---

## 23. Optional V2 phases

### V2-A — Assisted extraction

Accept transcripts and generate candidates with evidence spans. Never auto-approve.

### V2-B — Conflict detection and temporal validity

Detect possible contradictions and add `valid_from`/`valid_until` with explicit resolution.

### V2-C — Rich provenance

Link memories to commits, issues, files, sessions, and URLs.

### V2-D — Curated document ingestion

Keep source documents separate from durable curated memory and preserve citations.

### V2-E — Backup and synchronization

Support Git-backed or user-selected sync and established encrypted backup tools.

### V2-F — Authenticated remote MCP

Only after a dedicated security design, support remote MCP for clients that cannot access the local machine. Do not expose the V1 localhost daemon directly to the public internet.

---

## 24. Suggested repository structure

```text
global-memory/
├── pyproject.toml
├── Makefile
├── README.md
├── CHANGELOG.md
├── SECURITY.md
├── CONTRIBUTING.md
├── contracts/
│   └── mcp/
│       └── v1/
│           ├── discovery.json
│           ├── tools/
│           ├── resources/
│           ├── prompts/
│           └── examples/
├── docs/
│   ├── architecture.md
│   ├── mcp-contract-v1.md
│   ├── configuration.md
│   ├── obsidian.md
│   ├── claude-code.md
│   ├── codex.md
│   ├── operations.md
│   ├── testing.md
│   └── adr/
├── integrations/
│   ├── skills/
│   │   └── global-memory/
│   │       ├── SKILL.md
│   │       └── references/
│   ├── claude-code/
│   │   └── CLAUDE.md.snippet
│   └── codex/
│       └── AGENTS.md.snippet
├── src/global_memory/
│   ├── __init__.py
│   ├── cli.py
│   ├── config.py
│   ├── errors.py
│   ├── logging.py
│   ├── domain/
│   │   ├── models.py
│   │   ├── lifecycle.py
│   │   ├── ranking.py
│   │   └── protocols.py
│   ├── application/
│   │   ├── memory_service.py
│   │   ├── search_service.py
│   │   ├── indexing_service.py
│   │   ├── project_service.py
│   │   └── diagnostics_service.py
│   ├── vault/
│   │   ├── repository.py
│   │   ├── markdown.py
│   │   ├── paths.py
│   │   ├── templates.py
│   │   └── watcher.py
│   ├── index/
│   │   ├── database.py
│   │   ├── migrations/
│   │   ├── fts.py
│   │   ├── chunks.py
│   │   ├── vectors.py
│   │   └── jobs.py
│   ├── embeddings/
│   │   ├── base.py
│   │   ├── ollama.py
│   │   └── fake.py
│   ├── retrieval/
│   │   ├── hybrid.py
│   │   ├── context.py
│   │   ├── pagination.py
│   │   └── excerpts.py
│   ├── projects/
│   │   ├── registry.py
│   │   ├── detector.py
│   │   └── git.py
│   ├── mcp/
│   │   ├── contract.py
│   │   ├── server.py
│   │   ├── daemon.py
│   │   ├── stdio_proxy.py
│   │   ├── tools.py
│   │   ├── resources.py
│   │   ├── prompts.py
│   │   └── errors.py
│   └── integrations/
│       ├── base.py
│       ├── manifest.py
│       ├── managed_files.py
│       ├── claude_code.py
│       └── codex.py
└── tests/
    ├── unit/
    ├── integration/
    ├── contract/
    ├── e2e/
    ├── live/
    ├── performance/
    └── fixtures/
```

---

## 25. Final definition of done

The implementation is complete when a user can:

1. Initialize a global Obsidian memory Vault.
2. Start one local MCP daemon automatically at login.
3. Connect Claude Code and Codex through tested installers.
4. Use one shared Agent Skill in both clients.
5. Retrieve project-aware context before substantial work.
6. Save candidates from either client.
7. Review and edit them visually in Obsidian.
8. Approve, reject, supersede, archive, and link memories safely.
9. Retrieve exact identifiers and semantic concepts with project isolation.
10. Use MCP tools, resources, and prompts through stdio and Streamable HTTP.
11. Continue using keyword retrieval when semantic services are unavailable.
12. Delete all generated indexes and rebuild from Markdown.
13. Diagnose the Vault, indexes, MCP transports, contract, and client integrations with one command.
14. Upgrade and uninstall without losing Vault content or damaging unrelated client settings.
15. Retrieve a memory created through Claude Code from Codex, and vice versa.

The MCP contract is the stable product interface. The Markdown Vault is the durable memory. Everything else is a replaceable implementation detail.
