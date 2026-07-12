"""Protocol-pure stdio MCP proxy for the shared local HTTP daemon."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import anyio
import httpx
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from mcp import types
from mcp.client.streamable_http import streamable_http_client
from mcp.server import Server
from mcp.server.lowlevel.server import NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.shared.message import SessionMessage

from global_memory import __version__
from global_memory.errors import ErrorCode, GlobalMemoryError

from .contract import CONTRACT_VERSION, failure, load_discovery
from .daemon import read_token


def _health_url(endpoint: str) -> str:
    parsed = urlsplit(endpoint)
    return urlunsplit((parsed.scheme, parsed.netloc, "/health/ready", "", ""))


async def _daemon_ready(endpoint: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=0.5) as client:
            response = await client.get(_health_url(endpoint))
        return response.status_code == 200
    except httpx.HTTPError:
        return False


async def _pump(
    source: MemoryObjectReceiveStream[SessionMessage | Exception],
    destination: MemoryObjectSendStream[SessionMessage],
) -> None:
    async for item in source:
        if isinstance(item, Exception):
            raise item
        await destination.send(item)


async def _pump_until_closed(
    source: MemoryObjectReceiveStream[SessionMessage | Exception],
    destination: MemoryObjectSendStream[SessionMessage],
    cancel_scope: anyio.CancelScope,
) -> None:
    try:
        await _pump(source, destination)
    finally:
        await destination.aclose()
        cancel_scope.cancel()


async def _proxy(endpoint: str, token: str) -> None:
    headers = {"Authorization": f"Bearer {token}"}
    async with (
        httpx.AsyncClient(headers=headers) as client,
        streamable_http_client(endpoint, http_client=client) as remote,
        stdio_server() as local,
        anyio.create_task_group() as tasks,
    ):
        tasks.start_soon(_pump_until_closed, local[0], remote[1], tasks.cancel_scope)
        tasks.start_soon(_pump_until_closed, remote[0], local[1], tasks.cancel_scope)


def _unavailable_server(endpoint: str) -> Server[Any]:
    discovery = load_discovery()
    server: Server[Any] = Server("global-memory-proxy", version=__version__)

    @server.list_tools()  # type: ignore[no-untyped-call,untyped-decorator]
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name=item["name"],
                description=item["description"],
                inputSchema=item["inputSchema"],
                outputSchema=item["outputSchema"],
                _meta={"contract_version": CONTRACT_VERSION},
            )
            for item in discovery["tools"]
        ]

    @server.call_tool(validate_input=False)  # type: ignore[untyped-decorator]
    async def call_tool(_name: str, _arguments: dict[str, Any]) -> types.CallToolResult:
        envelope = failure(
            GlobalMemoryError(
                ErrorCode.DAEMON_UNAVAILABLE,
                "The shared Global Agent Memory daemon is unavailable.",
                retryable=True,
                details={"endpoint": endpoint},
                remediation="Start the daemon with `global-memory daemon start` and retry.",
            )
        )
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=json.dumps(envelope))],
            structuredContent=envelope,
            isError=True,
        )

    return server


async def _serve_unavailable(endpoint: str) -> None:
    server = _unavailable_server(endpoint)
    options = InitializationOptions(
        server_name="global-memory-proxy",
        server_version=__version__,
        capabilities=server.get_capabilities(notification_options=NotificationOptions(), experimental_capabilities={}),
    )
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, options, raise_exceptions=False)


async def run_proxy(endpoint: str, token_file: Path) -> None:
    token = read_token(token_file)
    if not await _daemon_ready(endpoint):
        await _serve_unavailable(endpoint)
        return
    try:
        await _proxy(endpoint, token)
    except (httpx.HTTPError, OSError):
        await _serve_unavailable(endpoint)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Proxy stdio MCP to the shared Global Agent Memory daemon.")
    parser.add_argument("--endpoint", default="http://127.0.0.1:8765/mcp/")
    parser.add_argument("--token-file", type=Path, required=True)
    return parser


def main() -> None:
    """Console-script entry point; stdout is exclusively owned by MCP stdio."""
    args = _parser().parse_args()
    try:
        asyncio.run(run_proxy(args.endpoint, args.token_file))
    except GlobalMemoryError as exc:
        raise SystemExit(f"{exc.code.value}: {exc.message}") from exc


if __name__ == "__main__":
    main()
