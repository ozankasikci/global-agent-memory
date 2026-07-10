from __future__ import annotations

import json
import resource
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamable_http_client

from global_memory.domain.models import MemoryMetadata
from global_memory.embeddings.fake import FakeEmbeddingProvider
from global_memory.index.database import IndexDatabase
from global_memory.index.indexer import Indexer
from global_memory.index.vectors import FakeVectorStore
from global_memory.retrieval.search import SearchRequest, SearchService
from global_memory.vault.markdown import render_note

pytestmark = pytest.mark.performance
NOW = datetime(2026, 7, 11, tzinfo=UTC)


def _p95(values: list[float]) -> float:
    return sorted(values)[max(0, int(len(values) * 0.95) - 1)]


def test_ten_thousand_note_search_and_incremental_budgets(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    notes = vault / "10 Global/Reusable Knowledge"
    notes.mkdir(parents=True)
    for index in range(10_000):
        metadata = MemoryMetadata.model_validate(
            {
                "id": f"mem_perf_{index:05d}",
                "title": f"Performance note {index}",
                "type": "fact",
                "scope": "global",
                "status": "active",
                "confidence": 0.8,
                "importance": 0.5,
                "created_at": NOW,
                "updated_at": NOW,
                "tags": ["benchmark", f"bucket-{index % 20}"],
                "links": [],
                "source_kind": "synthetic",
                "supersedes": [],
            }
        )
        (notes / f"note-{index:05d}.md").write_text(
            render_note(metadata, f"Synthetic conveyor recovery procedure number {index}.\n")
        )
    database = IndexDatabase(tmp_path / "state/memory.db")
    indexer = Indexer(vault, database)
    started = time.perf_counter()
    report = indexer.full_reindex()
    full_index_seconds = time.perf_counter() - started
    assert report.indexed == 10_000

    fts_latencies: list[float] = []
    for _ in range(40):
        started = time.perf_counter()
        assert indexer.keyword_search("conveyor recovery", limit=20)
        fts_latencies.append(time.perf_counter() - started)
    fts_p95 = _p95(fts_latencies)

    changed = notes / "note-05000.md"
    changed.write_text(changed.read_text().replace("conveyor recovery", "instant reconciliation"))
    started = time.perf_counter()
    indexer.index_path(changed.relative_to(vault))
    incremental_seconds = time.perf_counter() - started
    assert indexer.keyword_search("instant reconciliation")

    vectors = FakeVectorStore()
    for row in database.connection.execute("SELECT id, content_hash FROM chunks LIMIT 100").fetchall():
        vectors.upsert(row["id"], "fake", "benchmark", row["content_hash"], [1.0, 0.0])
    hybrid = SearchService(
        database,
        indexer,
        embedding_provider=FakeEmbeddingProvider(model="benchmark", dimension=2),
        vectors=vectors,
    )
    hybrid_latencies: list[float] = []
    for _ in range(40):
        started = time.perf_counter()
        assert hybrid.search(SearchRequest(query="conveyor recovery", mode="hybrid")).results
        hybrid_latencies.append(time.perf_counter() - started)
    hybrid_p95 = _p95(hybrid_latencies)
    raw_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    max_rss_mib = raw_rss / 1024 / 1024 if sys.platform == "darwin" else raw_rss / 1024
    metrics = {
        "notes": 10_000,
        "full_index_seconds": round(full_index_seconds, 4),
        "incremental_seconds": round(incremental_seconds, 4),
        "fts_p95_ms": round(fts_p95 * 1000, 3),
        "hybrid_p95_ms": round(hybrid_p95 * 1000, 3),
        "database_mib": round(database.path.stat().st_size / 1024 / 1024, 3),
        "max_rss_mib": round(max_rss_mib, 3),
    }
    print("PERFORMANCE_METRICS " + json.dumps(metrics, sort_keys=True))
    assert incremental_seconds < 3
    assert fts_p95 < 0.150
    assert hybrid_p95 < 0.750


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@contextmanager
def _daemon(tmp_path: Path):
    port = _free_port()
    token_file = tmp_path / "token"
    token_file.write_text("performance-token\n")
    token_file.chmod(0o600)
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "global_memory.mcp.daemon",
            "--vault",
            str(tmp_path / "transport-vault"),
            "--state",
            str(tmp_path / "transport-state"),
            "--token-file",
            str(token_file),
            "--port",
            str(port),
            "--no-watch",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                if httpx.get(base + "/health/ready", timeout=0.2).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.05)
        else:
            raise RuntimeError("performance daemon failed to start")
        yield base + "/mcp/", token_file
    finally:
        process.terminate()
        process.wait(timeout=5)


@pytest.mark.asyncio
async def test_stdio_proxy_overhead_budget(tmp_path: Path) -> None:
    with _daemon(tmp_path) as (endpoint, token_file):
        token = token_file.read_text().strip()
        async with (
            httpx.AsyncClient(headers={"Authorization": f"Bearer {token}"}) as client,
            streamable_http_client(endpoint, http_client=client) as (direct_read, direct_write, _),
            ClientSession(direct_read, direct_write) as direct,
        ):
            await direct.initialize()
            direct_latencies = []
            for _ in range(30):
                started = time.perf_counter()
                await direct.call_tool("memory_status", {})
                direct_latencies.append(time.perf_counter() - started)
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
            stdio_client(params) as (proxy_read, proxy_write),
            ClientSession(proxy_read, proxy_write) as proxy,
        ):
            await proxy.initialize()
            proxy_latencies = []
            for _ in range(30):
                started = time.perf_counter()
                await proxy.call_tool("memory_status", {})
                proxy_latencies.append(time.perf_counter() - started)
        overhead = _p95(proxy_latencies) - _p95(direct_latencies)
        print(
            "TRANSPORT_METRICS "
            + json.dumps(
                {
                    "direct_p95_ms": round(_p95(direct_latencies) * 1000, 3),
                    "proxy_p95_ms": round(_p95(proxy_latencies) * 1000, 3),
                    "proxy_overhead_p95_ms": round(overhead * 1000, 3),
                },
                sort_keys=True,
            )
        )
        assert overhead < 0.100
