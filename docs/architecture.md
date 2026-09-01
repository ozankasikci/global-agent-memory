# Architecture

Dependency direction is transport and client adapters → application services → domain. Vault, SQLite, vectors, embeddings, Git, Watchdog, and client integrations implement ports owned by the application/domain layers. The domain imports none of those adapters.

`global-memory-mcp` is a hybrid stdio bridge. It prefers a healthy local `global-memoryd`
process and otherwise constructs the same MCP server and application container
in-process. Both modes preserve the frozen MCP V1 contract, access controls, mutation
idempotency, project isolation, and audit behavior.

Markdown in the Vault is canonical. SQLite FTS, vectors, queues, access requests, grants,
and mutation receipts are local generated or operational state. Multiple processes use
WAL mode, a bounded busy timeout, and serialized migrations. Daemonless runtimes
reconcile external Markdown edits at a bounded request-time cadence.

The optional daemon owns continuous Vault watching, background embedding retries,
Streamable HTTP, and authenticated dashboard sessions. The dashboard command and
`memory_dashboard_open` start it on demand when it is not already running. Installing a
launchd or systemd service is an optimization, not a requirement for agent memory.
