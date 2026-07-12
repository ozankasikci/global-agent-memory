# Configuration

Configuration uses OS-native locations selected by `platformdirs`; generated indexes, logs, locks, and the protected local token remain outside the Vault. Values resolve in this order: configuration file, `GLOBAL_MEMORY_` environment variables, then CLI overrides. Nested environment fields use `__`, for example `GLOBAL_MEMORY_MCP__PORT=9000`.

V1 network binding is restricted to `127.0.0.1`. The local bearer token is generated with user-only permissions and is never written to the Vault or emitted by configuration display commands.

Initialization creates missing managed folders and files but preserves any existing Vault README or configuration file.
