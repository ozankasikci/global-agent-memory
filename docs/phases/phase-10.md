# Phase 10 report — shared daemon and stdio MCP proxy

## Completed requirements

`global-memoryd` runs the frozen MCP V1 server over the official SDK's Streamable HTTP session manager and binds only to `127.0.0.1`. The transport requires the protected bearer token, uses SDK host/origin validation, limits request bytes and concurrent connections, and exposes only `/mcp/`, `/health/live`, and `/health/ready`. The service continues to start when no semantic provider is available because the application stack already degrades to keyword retrieval.

`global-memory-mcp` is a raw MCP message proxy between stdio and Streamable HTTP. Passing `SessionMessage` values unchanged preserves discovery, JSON-RPC request IDs, notifications, cancellation, structured results, resources, and prompts. stdout belongs only to the SDK stdio transport. If readiness fails, the proxy starts a frozen-discovery fallback server whose tool calls return the stable retryable `DAEMON_UNAVAILABLE` envelope.

The two pumps close their destination streams and cancel the sibling pump when either transport ends. An explicit subprocess test closes stdin without an MCP shutdown exchange and proves the proxy exits successfully without writing non-protocol output.

Managed start/status/stop records a random instance identity alongside the PID and verifies it against the daemon health response before reusing or signalling the process. This avoids treating a recycled PID as this product's daemon. Start is idempotent and readiness-gated; stop never escalates to an unrelated force-kill. The initial `status` and `search` CLI runtime commands use the official MCP client adapter rather than opening SQLite or the Vault directly.

## Files and tests

Transport code is under `src/global_memory/mcp/daemon.py`, `stdio_proxy.py`, `client.py`, and `daemon_control.py`. The console scripts are `global-memoryd` and `global-memory-mcp`; managed lifecycle is exposed under `global-memory daemon`.

`tests/e2e/test_transports.py` starts a real temporary daemon and proves authenticated discovery/calls, shared state across independent clients, request-size and Host rejection, stdio discovery/calls, protocol purity through the official client parser, cancellation-object preservation, clean stdin-close exit, stable daemon-unavailable calls, and a subprocess CLI status call through MCP. `tests/e2e/test_daemon_control.py` proves idempotent start, verified status, clean stop, and repeated stop.

## Commands and results

- `uv run pytest -q tests/e2e` — 5 passed.
- `make check` — Ruff formatting/lint and strict mypy passed; 36 unit, 25 integration, 14 contract, and 5 E2E tests passed; deterministic contract regeneration passed.

## Known limitations and next phase

The daemon currently reports its watcher as not started; Phase 12 owns watcher leadership, debouncing, reconciliation, and recovery. Phase 13 expands the CLI beyond the first MCP-routed runtime commands and installs native user services.

Reference: [official MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk).
