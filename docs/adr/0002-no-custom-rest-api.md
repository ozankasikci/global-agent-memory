# ADR 0002: No custom REST API in V1

- Status: accepted
- Date: 2026-07-11

Streamable HTTP remains the only supported machine-to-machine memory API through MCP. Minimal liveness/readiness routes and private dashboard UI endpoints may be served by the daemon when they are localhost-only, session-authenticated, and explicitly excluded from the compatibility contract. No public or independently supported JSON REST API will be introduced in V1.

This avoids two competing public contracts while allowing a first-party browser interface. CLI and AI-agent operations still discover and launch the UI through MCP.
