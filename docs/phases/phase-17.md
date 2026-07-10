# Phase 17 report — security, privacy, and performance hardening

## Security and privacy controls

`SECURITY.md` models untrusted local clients, DNS rebinding/origin attacks, LAN exposure, traversal and symlink escape, malicious YAML, prompt injection, secrets, oversized requests, duplicate identities, generated-state corruption, and client-config modification. It documents controls and residual risks instead of implying a same-user local daemon is a multi-user security boundary.

Candidate creation and updates reject common private-key, OpenAI-style key, AWS access-key, password/token assignment, and bearer-token patterns before persistence. Failures disclose only a boolean detection marker. Structured JSON logging recursively redacts content/body/prompt/embedding/authorization/secret/token/password fields plus inline bearer/key shapes. Daemon lifecycle logs contain only host and port. Audit/index events remain content-free.

Stored Markdown remains explicitly untrusted data: safe YAML rejects object constructors, context bundles prepend the untrusted-text boundary and label every item, and a prompt-injection note is returned inert rather than interpreted by a service. Property/corpus tests cover arbitrary traversal inputs, absolute paths and symlink escape; existing E2E covers invalid token, Host rejection, oversized bodies, localhost-only CLI/config, and outside-Vault writes. Integration tests prove unmanaged config is never adopted or overwritten.

## Performance evidence

`make performance` generated and indexed 10,000 synthetic notes, ran 40 warm FTS and hybrid samples, measured an incremental note change, and compared 30 direct HTTP calls with 30 calls through the real stdio proxy.

- Full rebuild: 35.9289 s; database 14.938 MiB; peak RSS approximately 135.656 MiB.
- Changed note searchable: 9.3 ms (budget 3,000 ms).
- Warm FTS P95: 56.975 ms (budget 150 ms).
- Warm fake-embedding hybrid P95: 75.166 ms (budget 750 ms).
- Direct HTTP P95: 4.126 ms; stdio proxy P95: 4.910 ms; overhead 0.784 ms (budget 100 ms).

All budgets pass with no unexplained regression. `docs/performance-baseline.md` records the reproducible baseline and which metrics are hard gates.

## Tests and next phase

Focused adversarial tests passed (21 tests). The opt-in performance suite passed 2 tests in 49.95 seconds. Phase 18 runs the final combined acceptance matrix, coverage/release audit, and records any external live-client blockers before V1 can be tagged.

The in-process domain/application/persistence coverage gate excludes only subprocess-tested CLI/daemon/stdio/watcher/client-control adapters and passes at 87.56% (110 tests). `make check` now enforces the 85% threshold.
