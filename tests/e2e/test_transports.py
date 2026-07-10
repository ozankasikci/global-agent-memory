from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import httpx
import pytest
from anyio import run_process
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamable_http_client

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@contextmanager
def daemon(tmp_path: Path):
    port = free_port()
    token = "test-local-token"
    token_file = tmp_path / "auth-token"
    token_file.write_text(token + "\n")
    token_file.chmod(0o600)
    log = (tmp_path / "daemon.log").open("w+")
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "global_memory.mcp.daemon",
            "--vault",
            str(tmp_path / "vault"),
            "--state",
            str(tmp_path / "state"),
            "--token-file",
            str(token_file),
            "--port",
            str(port),
            "--max-request-bytes",
            "2048",
        ],
        stdout=log,
        stderr=log,
        text=True,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if process.poll() is not None:
                log.seek(0)
                raise AssertionError(f"daemon exited early:\n{log.read()}")
            try:
                if httpx.get(f"{base}/health/ready", timeout=0.2).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.05)
        else:
            raise AssertionError("daemon did not become ready")
        yield process, f"{base}/mcp/", token, token_file
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        log.close()


async def http_session(endpoint: str, token: str):
    client = httpx.AsyncClient(headers={"Authorization": f"Bearer {token}"})
    transport = streamable_http_client(endpoint, http_client=client)
    streams = await transport.__aenter__()
    session = ClientSession(streams[0], streams[1])
    await session.__aenter__()
    await session.initialize()
    return client, transport, session


async def close_http_session(client, transport, session) -> None:
    await session.__aexit__(None, None, None)
    await transport.__aexit__(None, None, None)
    await client.aclose()


async def test_authenticated_http_two_clients_share_state_and_security_limits(tmp_path: Path) -> None:
    with daemon(tmp_path) as (_, endpoint, token, _):
        client_one, transport_one, session_one = await http_session(endpoint, token)
        try:
            remembered = await session_one.call_tool(
                "memory_remember",
                {
                    "request_id": "http-create",
                    "title": "Shared convention",
                    "content": "All clients share this daemon memory.",
                    "type": "convention",
                    "scope": "global",
                },
            )
            data = remembered.structuredContent["data"]
            approved = await session_one.call_tool(
                "memory_approve",
                {
                    "request_id": "http-approve",
                    "id": data["metadata"]["id"],
                    "expected_updated_at": data["version"],
                },
            )
            assert approved.structuredContent["data"]["metadata"]["status"] == "active"
        finally:
            await close_http_session(client_one, transport_one, session_one)

        client_two, transport_two, session_two = await http_session(endpoint, token)
        try:
            found = await session_two.call_tool("memory_search", {"query": "share daemon", "mode": "keyword"})
            assert found.structuredContent["data"]["results"][0]["title"] == "Shared convention"
            status = await session_two.call_tool("memory_status", {})
            assert status.structuredContent["data"]["transport"] == "streamable-http"
        finally:
            await close_http_session(client_two, transport_two, session_two)

        async with httpx.AsyncClient() as security_client:
            unauthorized = await security_client.post(
                endpoint, content=b"{}", headers={"Authorization": "Bearer wrong"}
            )
            oversized = await security_client.post(
                endpoint,
                content=b"x" * 4096,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            )
            bad_host = await security_client.post(
                endpoint,
                content=b"{}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "Host": "evil.example",
                },
            )
        assert unauthorized.status_code == 401
        assert unauthorized.json()["error"]["code"] == "UNAUTHORIZED"
        assert oversized.status_code == 413
        assert oversized.json()["error"]["code"] == "REQUEST_TOO_LARGE"
        assert bad_host.status_code == 421


async def test_stdio_proxy_is_protocol_pure_and_shares_daemon(tmp_path: Path) -> None:
    with daemon(tmp_path) as (_, endpoint, _token, token_file):
        error_log = (tmp_path / "proxy.stderr").open("w+")
        params = StdioServerParameters(
            command=sys.executable,
            args=[
                "-m",
                "global_memory.mcp.stdio_proxy",
                "--endpoint",
                endpoint,
                "--token-file",
                str(token_file),
            ],
        )
        async with (
            stdio_client(params, errlog=error_log) as (read_stream, write_stream),
            ClientSession(read_stream, write_stream) as session,
        ):
            await session.initialize()
            tools = await session.list_tools()
            assert "memory_status" in {tool.name for tool in tools.tools}
            status = await session.call_tool("memory_status", {})
            assert not status.isError
            assert status.structuredContent["data"]["transport"] == "streamable-http"
        error_log.close()


async def test_cli_runtime_status_calls_the_mcp_daemon(tmp_path: Path) -> None:
    with daemon(tmp_path) as (_, endpoint, _token, token_file):
        result = await run_process(
            [
                sys.executable,
                "-m",
                "global_memory.cli",
                "status",
                "--endpoint",
                endpoint,
                "--token-file",
                str(token_file),
            ]
        )
        envelope = json.loads(result.stdout)
        assert envelope["ok"] is True
        assert envelope["data"]["transport"] == "streamable-http"


async def test_stdio_proxy_reports_daemon_unavailable_with_stable_error(tmp_path: Path) -> None:
    port = free_port()
    token_file = tmp_path / "auth-token"
    token_file.write_text("token\n")
    params = StdioServerParameters(
        command=sys.executable,
        args=[
            "-m",
            "global_memory.mcp.stdio_proxy",
            "--endpoint",
            f"http://127.0.0.1:{port}/mcp/",
            "--token-file",
            str(token_file),
        ],
    )
    async with (
        stdio_client(params) as (read_stream, write_stream),
        ClientSession(read_stream, write_stream) as session,
    ):
        await session.initialize()
        result = await session.call_tool("memory_status", {})
        assert result.isError and result.structuredContent
        assert result.structuredContent["error"]["code"] == "DAEMON_UNAVAILABLE"
