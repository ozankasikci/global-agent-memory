# ADR 0005: Hybrid daemonless MCP runtime

- Status: accepted
- Date: 2026-08-30

## Context

Coding clients launch stdio MCP processes naturally, but the original bridge required a
separate HTTP daemon to be alive before any memory tool could run. A stopped or restarted
daemon therefore appeared to clients as `Session terminated`, even though canonical
Markdown and all application services were available locally.

The dashboard still needs an HTTP origin and authenticated browser session. Continuous
Obsidian watching and background embedding retries also benefit from one shared process.
Those needs do not justify making every agent retrieval depend on that process.

## Decision

The stdio bridge prefers a ready local daemon and falls back to an in-process MCP server
when HTTP is unavailable. Runtime CLI commands use the same selection. The fallback uses
the existing application container and frozen V1 MCP contract rather than a separate file
or database API.

Daemonless runtimes reconcile external Markdown edits at request time. SQLite uses WAL,
a bounded busy timeout, and migration serialization for safe multi-process startup. The
dashboard tool starts the authenticated localhost daemon on demand, then requests its
one-time browser session through MCP.

The background daemon remains optional and valuable for continuous file watching,
background semantic indexing, shared HTTP clients, and the dashboard.

## Consequences

- Agent search, context, candidate, lifecycle, project, and access tools work without an
  always-running server.
- Protected and sealed memory enforcement remains identical because both modes share the
  same MCP adapter and application services.
- External Markdown edits are discovered on the next bounded refresh in daemonless mode,
  or immediately by the optional watcher.
- The dashboard remains localhost-only and token-authenticated.
- Markdown remains canonical and SQLite remains disposable and rebuildable.
