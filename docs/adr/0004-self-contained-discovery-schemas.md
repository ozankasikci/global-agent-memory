# ADR 0004: MCP discovery schemas are self-contained

- Status: accepted
- Date: 2026-07-11

The initial frozen discovery snapshot represented every tool output schema as a relative `$ref` to a repository file. MCP discovery provides no base URI or file-serving mechanism through which a client can resolve that reference, so otherwise conforming clients could not validate successful tool results.

Before the server implementation or V1 release, discovery was corrected to embed the unchanged common success-envelope schema. This changes no tool name, field, requirement, default, response shape, or semantic behavior. The separately committed envelope schema remains canonical and generation tests prove the embedded copies are identical in meaning.
