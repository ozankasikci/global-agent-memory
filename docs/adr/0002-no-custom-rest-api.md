# ADR 0002: No custom REST API in V1

- Status: accepted
- Date: 2026-07-11

Streamable HTTP is used only as an MCP transport. Minimal liveness or readiness routes may be added when required operationally, but no JSON REST endpoints for memory operations will be introduced in V1.

This avoids two competing public contracts and keeps authentication, errors, discovery, and lifecycle behavior consistent.
