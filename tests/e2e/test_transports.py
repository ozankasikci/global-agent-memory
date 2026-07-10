from __future__ import annotations

import asyncio
import json
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import pytest
from anyio import run_process
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamable_http_client

from global_memory.application.diagnostics_service import run_diagnostics
from global_memory.config import EmbeddingSettings, GlobalMemorySettings, MCPSettings, PlatformPaths
from global_memory.integrations.manager import ClientSpec, IntegrationManager
from global_memory.integrations.verify import verify_client

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


class _FakeClientRegistration:
    def __init__(self) -> None:
        self.registered: set[str] = set()

    def available(self, spec: ClientSpec) -> bool:
        return True

    def is_registered(self, spec: ClientSpec, command: list[str]) -> bool:
        del command
        return spec.name in self.registered

    def register(self, spec: ClientSpec, command: list[str]) -> None:
        del command
        self.registered.add(spec.name)

    def unregister(self, spec: ClientSpec) -> None:
        self.registered.remove(spec.name)


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
            "--embedding-provider",
            "fake",
            "--embedding-model",
            "e2e-fake",
            "--embedding-dimension",
            "16",
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


async def test_stdio_proxy_terminates_cleanly_when_stdin_closes(tmp_path: Path) -> None:
    with daemon(tmp_path) as (_, endpoint, _token, token_file):
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "global_memory.mcp.stdio_proxy",
            "--endpoint",
            endpoint,
            "--token-file",
            str(token_file),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        assert process.stdin is not None
        process.stdin.close()
        await process.stdin.wait_closed()
        try:
            return_code = await asyncio.wait_for(process.wait(), timeout=3)
            assert return_code == 0
            assert process.stdout is not None
            assert await process.stdout.read() == b""
        finally:
            if process.returncode is None:
                process.terminate()
                await process.wait()


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


async def test_subprocess_cli_memory_lifecycle_uses_mcp(tmp_path: Path) -> None:
    with daemon(tmp_path) as (_, endpoint, _token, token_file):
        common = ["--endpoint", endpoint, "--token-file", str(token_file)]
        remembered = await run_process(
            [
                sys.executable,
                "-m",
                "global_memory.cli",
                "remember",
                "CLI memory",
                "Created through the MCP CLI.",
                "--type",
                "fact",
                "--scope",
                "global",
                *common,
            ]
        )
        created = json.loads(remembered.stdout)["data"]
        fetched = await run_process(
            [sys.executable, "-m", "global_memory.cli", "get", created["metadata"]["id"], *common]
        )
        assert json.loads(fetched.stdout)["data"]["body"] == "Created through the MCP CLI."


async def test_watcher_indexes_rapid_external_obsidian_saves(tmp_path: Path) -> None:
    with daemon(tmp_path) as (_, endpoint, token, _token_file):
        client, transport, session = await http_session(endpoint, token)
        try:
            created = await session.call_tool(
                "memory_remember",
                {
                    "request_id": "watch-create",
                    "title": "Watcher note",
                    "content": "Original external body.",
                    "type": "fact",
                    "scope": "global",
                },
            )
            path = Path(created.structuredContent["data"]["path"])
            for body in ("First external body.", "Second external body.", "Final external body."):
                text = await asyncio.to_thread(path.read_text)
                start = text.index("\n---\n") + 5
                await asyncio.to_thread(path.write_text, text[:start] + body)
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                found = await session.call_tool(
                    "memory_search", {"query": "Final external", "mode": "keyword", "statuses": ["candidate"]}
                )
                if found.structuredContent["data"]["results"]:
                    break
                await asyncio.sleep(0.1)
            else:
                raise AssertionError("watcher did not index the final debounced save")
        finally:
            await close_http_session(client, transport, session)


async def test_doctor_verifies_direct_and_stdio_mcp_connectivity(tmp_path: Path) -> None:
    with daemon(tmp_path) as (_, endpoint, _token, token_file):
        port = urlsplit(endpoint).port
        assert port is not None
        settings = GlobalMemorySettings(
            vault_path=tmp_path / "vault",
            mcp=MCPSettings(port=port),
            embeddings=EmbeddingSettings(enabled=False),
        )
        paths = PlatformPaths(
            config_dir=tmp_path,
            data_dir=tmp_path / "state",
            log_dir=tmp_path / "logs",
            runtime_dir=tmp_path / "run",
        )
        assert paths.auth_token == token_file
        report = await run_diagnostics(settings, paths)
        transport = {check.name: check.status for check in report.checks}
        assert transport["daemon_readiness"] == "pass"
        assert transport["direct_mcp_discovery"] == "pass"
        assert transport["stdio_proxy"] == "pass"


async def test_both_client_installers_verify_shared_daemon_and_project_isolation(tmp_path: Path) -> None:
    with daemon(tmp_path) as (_, endpoint, _token, token_file):
        adapter = _FakeClientRegistration()
        manager = IntegrationManager(
            tmp_path / "home",
            tmp_path / "integration-state",
            adapter=adapter,
            endpoint=endpoint,
            token_file=token_file,
        )
        manager.install("claude-code", copy=True)
        manager.install("codex", copy=True)

        claude = await verify_client(manager, "claude-code")
        codex = await verify_client(manager, "codex")

        assert claude.ok, claude.checks
        assert codex.ok, codex.checks


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
