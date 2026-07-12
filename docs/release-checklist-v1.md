# V1 release checklist

- Date: 2026-07-12
- Package: `0.1.1`
- MCP contract: `v1`
- Status: **`v0.1.1` development release ready; a stable V1 release remains blocked on complete live client/UI acceptance.**

## Required product scenarios

| Scenario | Evidence | Status |
| --- | --- | --- |
| Cross-client shared memory | HTTP “Claude” session creates/edits/approves; independent stdio “Codex” session reads the same ID/body | Pass (adapter E2E) |
| Project isolation | Both installed client adapters run temporary-Git project detection and cross-project leakage smoke flow | Pass |
| Obsidian round trip | MCP candidate, direct Markdown edit, watcher visibility, approval, second-client read | Pass (filesystem-equivalent E2E) |
| Exact and semantic retrieval | Exact `VERSION_CONFLICT` keyword search plus daemon-wired fake-vector semantic search | Pass |
| Offline degradation | Unavailable embedding provider retains keyword search and lifecycle behavior; daemon startup is provider-optional | Pass |
| Rebuildability | Delete SQLite/WAL/SHM and recover equivalent visible memory from Markdown | Pass |
| Concurrency/idempotency | Two stale concurrent updates yield one success/one `VERSION_CONFLICT`; exact request replay is stable and changed payload conflicts | Pass |
| Recovery | Kill daemon immediately after external write; startup reconciliation indexes the durable Markdown edit | Pass |
| MCP contract/transports | Frozen discovery and every tool/resource/prompt through official harness; HTTP and stdio E2E | Pass |
| Shared skill | One validated canonical skill installed and hash-verified for both fake clients | Pass |
| Visualization | Templates/Bases YAML, project hubs, review workflow, reciprocal links and watcher tests | Pass (automated) |
| Security | Localhost/auth/Host/size/path/symlink/YAML/injection/secret/log/config checks | Pass |

## Release gates

| Gate | Evidence | Status |
| --- | --- | --- |
| Ruff + strict mypy | `make check` | Pass |
| Unit / integration / contract / E2E | 60 / 44 / 16 / 13 | Pass |
| Coverage | In-process target excludes subprocess-only adapters; final result 87.39% | Pass |
| Performance | 10k-note suite, all four budgets pass | Pass |
| Fresh install/upgrade/docs | Isolated wheel, console scripts, schema upgrade fixture, operations/client docs | Pass |
| Linux/macOS, Python 3.12/3.14 | Matrix configured; full gate passed locally on macOS 3.12.11 and 3.14.0rc3 | Awaiting Linux/remote CI run |
| Claude Code live invocation/uninstall | Requires explicit permission to modify real user scope | Not run |
| Codex live invocation/uninstall | Local npm wrapper fails with missing bundled native binary (`ENOENT`) | Blocked externally |
| Obsidian properties/Bases/graph visual inspection | Obsidian installed; opening/mutating a user-selected Vault requires explicit permission | Not run |
| `doctor` on release installation | Covered with offline and real-daemon/stdin transport fixtures | Pass (automated) |
| Critical/high known product bug | No automated critical/high failure remains | Pass |

## Release-machine client inventory

Recorded read-only on 2026-07-11; no client configuration or Vault was changed.

| Client | Discovered version | Live acceptance state |
| --- | --- | --- |
| Claude Code | 2.1.185 | Executable works; install/invoke/uninstall remains authorization-gated |
| Codex | npm wrapper 0.116.0 | `--version` fails with `ENOENT` for the missing `codex-darwin-arm64` native executable |
| Obsidian | 1.8.10 | Application is installed; visual Vault acceptance remains authorization-gated |

`git remote -v` returns no configured remote in this checkout, so the required remote CI matrix cannot be triggered here.

Do not tag V1 until every awaiting/not-run/blocked live gate above is resolved and the command outputs/client versions are appended without secrets.
