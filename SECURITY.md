# Security and privacy

## Supported boundary

Global Memory is a single-user local service. The daemon binds only to `127.0.0.1`, requires a generated bearer token, validates Host/Origin, limits request bytes and concurrent connections, and exposes no public memory REST API. Do not expose the V1 daemon through port forwarding, a LAN bind, or a public reverse proxy.

Markdown is canonical and is treated as untrusted data. Retrieved text can contain prompt injection; context output labels it as untrusted stored note text and never promotes it to server or skill instructions. YAML uses a safe loader and a closed validated lifecycle model. Probable credentials are rejected before memory creation/update, and structured logs recursively redact content, prompts, embeddings, authorization, passwords, secrets, and token-shaped strings.

## Threat model

| Threat | Control | Residual risk |
| --- | --- | --- |
| Untrusted local MCP client | Bearer token, localhost-only bind, bounded requests/connections | Any process running as the same user may be able to read the token file. OS account isolation remains required. |
| DNS rebinding / forged browser origin | SDK Host and Origin allowlists | A compromised same-user process is outside browser-origin protection. |
| Accidental LAN/public exposure | Host is a literal `127.0.0.1` configuration type and daemon CLI choice | Deliberate tunneling can defeat this boundary; remote hosting is unsupported. |
| Traversal, absolute paths, symlink escape | Central resolved Vault confinement for reads/writes, property-based corpus | A compromised Vault directory or OS filesystem layer remains trusted at the account boundary. |
| Malicious YAML/frontmatter | `yaml.safe_load`, Pydantic validation, invalid-note isolation | Markdown body remains arbitrary untrusted text by design. |
| Prompt injection in notes | Explicit untrusted-data flags/header, client-neutral skill rules, no instruction execution in services | A downstream model may still mishandle data; users should review high-impact actions. |
| Secrets in notes/logs | Candidate/update secret scanner, content-free audit records, recursive log redaction | Pattern detection is heuristic and cannot recognize every secret format. Do not use the Vault as a secret store. |
| Oversized/abusive requests | Byte limit and Uvicorn concurrency limit | Local denial of service by the same OS user cannot be eliminated completely. |
| Duplicate IDs / malicious copies | Quarantine from search, explicit diagnostics, no silent selection | Manual conflict resolution is required. |
| Client config damage | Official client CLIs preferred; backups, exact markers/hashes, manifest ownership, unmanaged conflict refusal | Client CLI behavior can change; inspect dry-run/status after client upgrades. |
| Generated database corruption | Integrity check, quarantine, rebuild from Markdown | Recent generated-only diagnostics may be lost; durable notes are retained. |

## Reporting

Do not include real credentials, bearer tokens, private note bodies, or user configuration contents in a report. Provide a minimal reproducer with synthetic data and the package/contract versions.
