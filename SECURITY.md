# Security

Report security issues privately to the maintainers rather than opening a public issue.

Global Memory is local-only in V1. Streamable HTTP binds to `127.0.0.1` and requires a protected local token. Vault note content is untrusted data. The service must reject traversal and symlink escapes, redact secrets from logs, and never expose raw tokens, indexes, vectors, or runtime logs through MCP.
