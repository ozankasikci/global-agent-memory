# MCP Contract V1

The generated files under `contracts/mcp/v1/` are the frozen public AI-facing contract for Global Memory V1. `discovery.json` is the golden capability snapshot. Individual tool, resource, and prompt files are generated from the same canonical definition for inspection and compatibility checks.

Every successful response uses the V1 success envelope and every domain failure uses the V1 error envelope. All mutation operations are idempotent by `request_id`. Candidate creation can never directly create active memory.

V1 permits additive optional response fields. Removing a field, changing a default or meaning, or making an optional field required needs a parallel major contract and a contract-change ADR. The JSON schemas are regenerated with `python scripts/generate_contract.py`; CI fails if regeneration changes committed files.

The MCP interface is the only public AI API. The service does not expose a parallel memory REST contract, and clients never access the Vault or generated indexes directly.
