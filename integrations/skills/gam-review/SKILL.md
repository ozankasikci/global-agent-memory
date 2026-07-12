---
name: gam-review
description: Show the Global Agent Memory candidate review queue without approving, rejecting, or mutating memories.
---

# GAM Review

1. Read the `memory://v1/candidates` MCP resource.
2. Filter to the detected current project unless the user explicitly requests all projects.
3. Summarize each candidate with title, type, project, confidence, candidate ID, and Vault-relative path.
4. Do not approve or reject anything. If the user wants to act on the queue, offer to open the dashboard with `memory_dashboard_open`.
