"""Small official-SDK client adapter used by runtime CLI commands."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from global_memory.errors import ErrorCode, GlobalMemoryError

from .daemon import read_token


async def call_http_tool(endpoint: str, token_file: Path, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Invoke one MCP tool and return its common V1 envelope."""
    token = read_token(token_file)
    try:
        async with (
            httpx.AsyncClient(headers={"Authorization": f"Bearer {token}"}) as client,
            streamable_http_client(endpoint, http_client=client) as (read_stream, write_stream, _),
            ClientSession(read_stream, write_stream) as session,
        ):
            await session.initialize()
            result = await session.call_tool(name, arguments)
    except (httpx.HTTPError, OSError) as exc:
        raise GlobalMemoryError(
            ErrorCode.DAEMON_UNAVAILABLE,
            "The shared Global Memory daemon is unavailable.",
            retryable=True,
            details={"endpoint": endpoint},
            remediation="Start the daemon with `global-memory daemon start` and retry.",
        ) from exc
    envelope = result.structuredContent
    if not isinstance(envelope, dict):
        raise GlobalMemoryError(
            ErrorCode.INTERNAL_ERROR,
            "The daemon returned a tool result without the V1 structured envelope.",
        )
    return envelope
