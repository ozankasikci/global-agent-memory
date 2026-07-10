from __future__ import annotations

import asyncio
import sys
from contextlib import suppress
from pathlib import Path

import pytest
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from tests.e2e.test_transports import close_http_session, daemon, http_session

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


async def _wait_for_search(session: ClientSession, query: str, *, status: str = "active") -> dict:
    deadline = asyncio.get_running_loop().time() + 5
    while asyncio.get_running_loop().time() < deadline:
        found = await session.call_tool(
            "memory_search",
            {"query": query, "mode": "keyword", "statuses": [status]},
        )
        results = found.structuredContent["data"]["results"]
        if results:
            return results[0]
        await asyncio.sleep(0.1)
    raise AssertionError(f"memory did not become searchable: {query}")


async def test_cross_client_obsidian_round_trip_exact_semantic_and_concurrency(tmp_path: Path) -> None:
    with daemon(tmp_path) as (_, endpoint, token, token_file):
        client, transport, claude = await http_session(endpoint, token)
        try:
            remembered = await claude.call_tool(
                "memory_remember",
                {
                    "request_id": "accept-create",
                    "title": "Shared release memory",
                    "content": "Initial body with VERSION_CONFLICT recovery procedure.",
                    "type": "solution",
                    "scope": "global",
                },
            )
            created = remembered.structuredContent["data"]
            path = Path(created["path"])
            text = await asyncio.to_thread(path.read_text)
            await asyncio.to_thread(
                path.write_text,
                text.replace("Initial body", "Obsidian edited body"),
            )
            await _wait_for_search(claude, "Obsidian edited", status="candidate")
            approved = await claude.call_tool(
                "memory_approve",
                {
                    "request_id": "accept-approve",
                    "id": created["metadata"]["id"],
                    "expected_updated_at": created["version"],
                },
            )
            active = approved.structuredContent["data"]
            status = await claude.call_tool("memory_status", {})
            assert status.structuredContent["data"]["embedding_state"] == "configured"
            assert status.structuredContent["data"]["keyword_only"] is False

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
                stdio_client(params) as (read_stream, write_stream),
                ClientSession(read_stream, write_stream) as codex,
            ):
                await codex.initialize()
                fetched = await codex.call_tool("memory_get", {"id": active["metadata"]["id"]})
                assert fetched.structuredContent["data"]["body"].startswith("Obsidian edited body")
                exact = await codex.call_tool("memory_search", {"query": "VERSION_CONFLICT", "mode": "keyword"})
                assert exact.structuredContent["data"]["results"]
                semantic = await codex.call_tool(
                    "memory_search",
                    {"query": "Obsidian edited body with VERSION_CONFLICT recovery procedure", "mode": "semantic"},
                )
                assert semantic.structuredContent["data"]["results"][0]["memory_id"] == active["metadata"]["id"]

                first, second = await asyncio.gather(
                    claude.call_tool(
                        "memory_update",
                        {
                            "request_id": "accept-update-a",
                            "id": active["metadata"]["id"],
                            "expected_updated_at": active["version"],
                            "body": "Concurrent winner A",
                        },
                    ),
                    codex.call_tool(
                        "memory_update",
                        {
                            "request_id": "accept-update-b",
                            "id": active["metadata"]["id"],
                            "expected_updated_at": active["version"],
                            "body": "Concurrent winner B",
                        },
                    ),
                )
                assert sorted([bool(first.isError), bool(second.isError)]) == [False, True]
                loser = first if first.isError else second
                assert loser.structuredContent["error"]["code"] == "VERSION_CONFLICT"

            replay = await claude.call_tool(
                "memory_remember",
                {
                    "request_id": "accept-replay",
                    "title": "Replay candidate",
                    "content": "Idempotent candidate body.",
                    "type": "fact",
                    "scope": "global",
                },
            )
            replayed = await claude.call_tool(
                "memory_remember",
                {
                    "request_id": "accept-replay",
                    "title": "Replay candidate",
                    "content": "Idempotent candidate body.",
                    "type": "fact",
                    "scope": "global",
                },
            )
            assert (
                replay.structuredContent["data"]["metadata"]["id"]
                == replayed.structuredContent["data"]["metadata"]["id"]
            )
            conflict = await claude.call_tool(
                "memory_remember",
                {
                    "request_id": "accept-replay",
                    "title": "Different payload",
                    "content": "Different body.",
                    "type": "fact",
                    "scope": "global",
                },
            )
            assert conflict.isError and conflict.structuredContent["error"]["code"] == "REQUEST_ID_CONFLICT"
        finally:
            await close_http_session(client, transport, claude)


async def test_crash_reconciliation_and_generated_database_rebuild(tmp_path: Path) -> None:
    memory_id: str
    with daemon(tmp_path) as (process, endpoint, token, _):
        client, transport, session = await http_session(endpoint, token)
        try:
            remembered = await session.call_tool(
                "memory_remember",
                {
                    "request_id": "recovery-create",
                    "title": "Recovery acceptance",
                    "content": "Before crash body.",
                    "type": "fact",
                    "scope": "global",
                },
            )
            candidate = remembered.structuredContent["data"]
            approved = await session.call_tool(
                "memory_approve",
                {
                    "request_id": "recovery-approve",
                    "id": candidate["metadata"]["id"],
                    "expected_updated_at": candidate["version"],
                },
            )
            active = approved.structuredContent["data"]
            memory_id = active["metadata"]["id"]
            path = Path(active["path"])
            text = await asyncio.to_thread(path.read_text)
            await asyncio.to_thread(path.write_text, text.replace("Before crash", "After crash"))
            process.kill()
            process.wait(timeout=5)
        finally:
            with suppress(Exception):
                await close_http_session(client, transport, session)

    with daemon(tmp_path) as (_, endpoint, token, _):
        client, transport, session = await http_session(endpoint, token)
        try:
            recovered = await _wait_for_search(session, "After crash")
            assert recovered["memory_id"] == memory_id
        finally:
            await close_http_session(client, transport, session)

    state = tmp_path / "state"
    for path in (state / "memory.db", state / "memory.db-wal", state / "memory.db-shm"):
        path.unlink(missing_ok=True)
    with daemon(tmp_path) as (_, endpoint, token, _):
        client, transport, session = await http_session(endpoint, token)
        try:
            rebuilt = await _wait_for_search(session, "After crash")
            assert rebuilt["memory_id"] == memory_id
        finally:
            await close_http_session(client, transport, session)
