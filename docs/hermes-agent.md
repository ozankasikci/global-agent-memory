# Hermes Agent integration

Hermes Agent can connect to Global Agent Memory through the local stdio proxy.
This is a manual client integration; the managed `global-memory setup` flow
currently targets Claude Code and Codex.

## Prerequisites

Install and initialize Global Agent Memory, then make sure its daemon is running:

```shell
global-memory status
```

Both `global-memory` and `hermes` must be available on `PATH`. A standard Hermes
installation includes MCP support.

## Add Global Agent Memory

Register the stdio proxy and accept the prompt to enable its 17 tools:

```shell
hermes mcp add global-memory \
  --connect-timeout 20 \
  --command global-memory \
  --args mcp proxy
```

`global-memory mcp proxy` connects to the default local endpoint and reads the
protected token from its platform-native configuration directory. The token value
is never copied into the Hermes configuration.

The command creates this entry in the Hermes `config.yaml`:

```yaml
mcp_servers:
  global-memory:
    command: global-memory
    args:
      - mcp
      - proxy
    connect_timeout: 20.0
    enabled: true
```

Start a new Hermes session after adding the server.

## Verify the integration

Check discovery from Hermes:

```shell
hermes mcp test global-memory
```

With Global Agent Memory `0.1.6`, a healthy connection reports 17 discovered tools,
including `memory_search`. For a retrieval smoke test, choose a distinctive phrase
from an existing Standard memory and ask Hermes:

```text
Use the global-memory MCP server's memory_search tool to search for
"<distinctive phrase>". Return the matching memory ID and title.
```

Hermes exposes the tool as `mcp__global_memory__memory_search`. The response should
contain the matching memory ID and title. If semantic search is unavailable, Global
Agent Memory may report its documented keyword fallback; this does not indicate an
MCP connection failure.

## Remove the integration

```shell
hermes mcp remove global-memory
hermes mcp list
```

Confirm the removal when prompted. This removes only the Hermes MCP registration;
it does not stop Global Agent Memory or delete stored memories.

## Troubleshooting

Hermes keeps the MCP SDK in an optional dependency group. The standard installer
includes it through the `all` extra. If a minimal source checkout reports that the
`mcp` Python SDK is missing, install the extra from the Hermes repository and retry:

```shell
uv pip install -e ".[mcp]"
```

## Tested versions

Tested on WSL2/Linux with:

- Hermes Agent `v0.20.6` (`2026.8.27`, upstream `e60983a6`)
- Global Agent Memory `0.1.6`

Verification covered tool discovery, a `memory_search` call through Hermes's MCP
runtime and the stdio proxy, and removal. The search returned the expected synthetic
memory ID and body.

Reference: [Hermes Agent MCP documentation](https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp).
