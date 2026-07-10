# Architecture

Dependency direction is transport and client adapters → application services → domain. Vault, SQLite, vectors, embeddings, Git, Watchdog, and client integrations implement ports owned by the application/domain layers. The domain imports none of those adapters.

One `global-memoryd` process will own the Vault watcher and generated indexes. Streamable HTTP-capable clients connect locally; other clients launch a thin `global-memory-mcp` stdio proxy. Both preserve the same frozen MCP V1 contract.
