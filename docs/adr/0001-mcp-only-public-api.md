# ADR 0001: MCP is the only public AI API

- Status: accepted
- Date: 2026-07-11

AI clients integrate through the versioned MCP contract. Administrative code may use internal application services, while runtime CLI operations use MCP. The local dashboard may use private, session-authenticated UI endpoints served by the same localhost daemon; those endpoints are implementation details, are not a supported client integration surface, and do not replace MCP. V1 will not expose a public custom memory REST API or direct index access.

This keeps Claude Code, Codex, and future clients on one behavior contract and prevents storage details from becoming public compatibility obligations.
