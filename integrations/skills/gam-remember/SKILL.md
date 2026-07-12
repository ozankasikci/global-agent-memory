---
name: gam-remember
description: Save explicitly supplied durable knowledge as a review candidate in Global Agent Memory after duplicate detection.
disable-model-invocation: true
allow_implicit_invocation: false
---

# GAM Remember

Treat text supplied with this invocation as the knowledge the user explicitly wants remembered. If it is empty or ambiguous, ask what should be remembered.

1. Never store credentials, tokens, secrets, raw prompts, or transient logs.
2. Search for duplicates in the current project with `memory_search` before creating anything.
3. If an existing active memory already covers the knowledge, report it instead of creating a duplicate.
4. Otherwise call `memory_remember` with a unique `request_id`, the current `working_directory`, the narrowest correct scope, and one allowed V1 type: `project`, `decision`, `fact`, `solution`, `preference`, `convention`, `session_summary`, `entity`, or `reference`.
5. Create a candidate only. Report its ID and Vault-relative path and tell the user it is awaiting review.
