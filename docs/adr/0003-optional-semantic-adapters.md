# ADR 0003: Semantic retrieval remains optional and adapter-bound

- Status: accepted
- Date: 2026-07-11

Keyword retrieval and every lifecycle operation remain usable without an embedding provider or vector extension. Embedding and vector behavior is expressed through application-owned protocols. Ollama uses the batched `/api/embed` endpoint, and sqlite-vec is loaded only inside its adapter.

sqlite-vec is pre-V1 and its language bindings are not covered by its SQL compatibility policy. V1 therefore constrains the dependency below `0.2`, tests the real extension, and prevents its module or virtual-table details from entering the MCP contract or domain layer. A failed provider or extension produces stable diagnostics and keyword-only operation, not service startup failure.

References: [Ollama embedding API](https://docs.ollama.com/api/embed), [sqlite-vec Python loading](https://alexgarcia.xyz/sqlite-vec/python.html), [sqlite-vec compatibility policy](https://alexgarcia.xyz/sqlite-vec/versioning.html).
