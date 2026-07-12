---
name: gam-search
description: Search Global Agent Memory in the current project for an exact fact, decision, error, convention, identifier, or known solution.
---

# GAM Search

Treat text supplied with this invocation as the search query. If it is empty, ask for a query.

1. Call `memory_search` with the query, current `working_directory`, `cross_project=false`, and a limit of 10.
2. Prefer `hybrid` mode; use `keyword` for an exact error, ID, path, or symbol.
3. Do not include candidates, rejected, archived, or superseded memories unless explicitly requested.
4. Return a concise result list with title, type, applicability, memory ID, and Vault-relative path.
5. Call `memory_get` before presenting a result as authoritative or using it to change the project.
