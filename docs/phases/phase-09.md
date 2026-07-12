# Phase 9 report — MCP application adapter and direct test server

## Completed requirements

The low-level official MCP SDK server exposes all 14 frozen tools, 10 resources/templates, and 6 prompts with exact committed names, descriptions, input schemas, output schemas, arguments, defaults, and contract metadata. Every tool returns the common success envelope; validation, domain, and unexpected failures return safe stable error envelopes through MCP-native error results. Adapters validate MCP input, call application services, and serialize results without leaking persistence types.

Every lifecycle tool, search/context/get/open/status/tags/reindex, and every project action routes through the shared application state. Project-scoped writes resolve explicit project or working-directory mappings instead of inferring from text. Runtime project and reindex mutations are guarded by request-ID receipts. Resource reads expose only allowed structured memory views. Prompts are client-neutral, validate required arguments, reference canonical capabilities, preserve isolation, require source attribution, and never auto-write memory.

## Files and tests

The generated contract loader/envelopes and server adapter are under `src/global_memory/mcp/`. `tests/contract/test_mcp_server.py` uses the official SDK `create_connected_server_and_client_session` harness. It proves byte-equivalent schema discovery, every resource and prompt call, all mandatory tool flows, candidate replay, update/approve/reject/supersede/archive/reindex, tags/projects, structured validation/domain errors, traversal rejection, and two-working-directory project isolation.

## Commands and results

- Contract tests first failed because the MCP package did not exist.
- SDK inspection exposed an unresolvable relative output-schema reference in frozen discovery. ADR 0004 records the non-semantic repair: discovery now embeds the unchanged success envelope.
- `uv run pytest tests/contract/test_mcp_server.py` — 5 passed through the official connected client after the final isolation scenario.
- `make check` before that final scenario — Ruff and strict mypy passed; 36 unit tests, 25 integration tests, and 13 contract tests passed; transport E2E remained explicitly deferred.

## Known limitations and next phase

This phase uses an in-memory official transport to isolate application-contract behavior. Phase 10 adds authenticated localhost Streamable HTTP, a protocol-pure stdio proxy, daemon lifecycle, request limits, cancellation/termination behavior, two independent clients, and runtime CLI calls through MCP.

Reference: [official MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk).
