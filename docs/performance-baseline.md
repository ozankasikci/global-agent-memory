# Performance baseline

Measured on 2026-07-11 on the current macOS ARM64 development machine with Python 3.12.11. The synthetic Vault contains 10,000 one-chunk Markdown notes. Semantic ranking uses deterministic fake embeddings so model startup/network time is excluded.

| Metric | Result | Initial budget |
| --- | ---: | ---: |
| Full keyword rebuild | 36.524 s | Recorded; no release ceiling |
| Single changed-note index + visibility | 14.6 ms | < 3,000 ms |
| Warm FTS P95 (40 calls) | 56.036 ms | < 150 ms |
| Warm hybrid P95 (40 calls) | 75.901 ms | < 750 ms |
| Direct Streamable HTTP status P95 | 4.824 ms | Recorded |
| stdio proxy status P95 | 6.309 ms | Recorded |
| stdio proxy incremental P95 overhead | 1.485 ms | < 100 ms |
| SQLite database size | 14.938 MiB | Recorded |
| Process peak RSS | 134.734 MiB | Recorded |

Run `make performance` to reproduce. The test fails on changed-note, FTS, hybrid, or proxy-overhead regression. Full rebuild, database size, and memory are recorded for trend comparison because machine/filesystem variance makes a hard V1 ceiling misleading.
