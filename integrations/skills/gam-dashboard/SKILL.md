---
name: gam-dashboard
description: Open the authenticated local Global Agent Memory dashboard when the user explicitly invokes this shortcut.
disable-model-invocation: true
allow_implicit_invocation: false
---

# GAM Dashboard

Call `memory_dashboard_open` with `open_browser=true`. The MCP runtime starts the
authenticated localhost dashboard server on demand when needed. Report success without
printing or inventing a dashboard URL.
