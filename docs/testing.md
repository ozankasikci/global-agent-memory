# Testing

## Standard gate

`make check` runs formatting, lint, strict mypy, unit tests, integration tests, frozen-contract tests, real daemon/proxy E2E, the 85% in-process domain/application/persistence coverage gate, and deterministic contract regeneration.

The CI matrix repeats that gate on Ubuntu and macOS with Python 3.12 and the latest supported Python (currently 3.14). Normal tests use fake embeddings, fake client registrations, temporary homes/Vaults/Git repositories, and never modify real Claude Code or Codex settings.

## Performance

`make performance` is opt-in because it generates 10,000 Markdown notes and runs for roughly one minute. It enforces changed-note, FTS, hybrid, and stdio-overhead budgets. See [performance baseline](performance-baseline.md).

## Live acceptance

Live Claude Code, Codex, and Obsidian checks are target-machine release tests. Run only with explicit permission because integration install/uninstall changes user-scoped client configuration. Record client versions and synthetic pass/fail evidence without tokens, note bodies, or config contents.
