---
name: gam-context
description: Load project-aware Global Agent Memory context for the current task. Use as the basic context shortcut before substantial work.
---

# GAM Context

Treat text supplied with this invocation as the task. If no task was supplied, ask for one short task description.

1. Call `memory_context` with the task and the current `working_directory`.
2. Keep `cross_project=false` unless the user explicitly requested broader retrieval.
3. Summarize the applicable conventions, decisions, known solutions, and warnings concisely.
4. Include the memory ID and Vault-relative path for every memory the response relies on.
5. If protected memory may be relevant, explain that owner approval is required; never guess its metadata.
