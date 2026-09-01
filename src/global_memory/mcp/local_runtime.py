"""Daemonless MCP runtime backed by canonical Markdown and disposable SQLite."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

from mcp.shared.memory import create_connected_server_and_client_session

from global_memory.config import GlobalMemorySettings, PlatformPaths, get_platform_paths, load_settings
from global_memory.embeddings.base import EmbeddingProvider
from global_memory.embeddings.ollama import OllamaEmbeddingProvider
from global_memory.errors import ErrorCode, GlobalMemoryError

from .client import call_http_tool, daemon_ready
from .daemon_control import start_daemon
from .server import ServiceContainer, build_container, create_mcp_server

DEFAULT_REFRESH_INTERVAL_SECONDS = 1.0


class IndexRefresh:
    """Reconcile external Markdown edits at a bounded request-time cadence."""

    def __init__(
        self,
        container: ServiceContainer,
        *,
        interval_seconds: float = DEFAULT_REFRESH_INTERVAL_SECONDS,
    ) -> None:
        self.container = container
        self.interval_seconds = interval_seconds
        self._last_refresh = time.monotonic()

    def __call__(self) -> None:
        now = time.monotonic()
        if now - self._last_refresh < self.interval_seconds:
            return
        self.container.index_jobs.reconcile()
        self.container.index_jobs.process_due()
        self._last_refresh = now


def _embedding_provider(settings: GlobalMemorySettings) -> EmbeddingProvider | None:
    if not settings.embeddings.enabled:
        return None
    return OllamaEmbeddingProvider(
        model=settings.embeddings.model,
        base_url=settings.embeddings.base_url,
        batch_size=settings.embeddings.batch_size,
        dimension=settings.embeddings.dimensions,
        timeout=1.0,
        max_retries=0,
    )


def _error_from_envelope(envelope: dict[str, Any]) -> GlobalMemoryError:
    payload = envelope.get("error") or {}
    raw_code = str(payload.get("code", ErrorCode.INTERNAL_ERROR.value))
    try:
        code = ErrorCode(raw_code)
    except ValueError:
        code = ErrorCode.INTERNAL_ERROR
    return GlobalMemoryError(
        code,
        str(payload.get("message", "The local memory operation failed.")),
        retryable=bool(payload.get("retryable", False)),
        details=payload.get("details") if isinstance(payload.get("details"), dict) else {},
        remediation=payload.get("remediation"),
    )


def build_local_container(
    settings: GlobalMemorySettings,
    paths: PlatformPaths,
    *,
    endpoint: str,
    token_file: Path,
    refresh_interval_seconds: float = DEFAULT_REFRESH_INTERVAL_SECONDS,
) -> ServiceContainer:
    """Build the regular application container without a watcher or HTTP dependency."""
    container = build_container(
        settings.vault_path,
        paths.data_dir,
        transport="stdio-direct",
        embedding_provider=_embedding_provider(settings),
        embedding_batch_size=settings.embeddings.batch_size,
        eager_embedding_sync=False,
    )
    container.watcher_state = "request-refresh"
    container.before_request = IndexRefresh(container, interval_seconds=refresh_interval_seconds)

    async def launch_dashboard(open_browser: bool) -> dict[str, Any]:
        selected_endpoint = endpoint
        selected_token = token_file
        if not await daemon_ready(selected_endpoint):
            state = await asyncio.to_thread(start_daemon, settings, paths)
            selected_endpoint = state.endpoint
            selected_token = paths.auth_token
        envelope = await call_http_tool(
            selected_endpoint,
            selected_token,
            "memory_dashboard_open",
            {"open_browser": open_browser},
        )
        if not envelope.get("ok"):
            raise _error_from_envelope(envelope)
        data = envelope.get("data")
        if not isinstance(data, dict):
            raise GlobalMemoryError(ErrorCode.INTERNAL_ERROR, "The dashboard launch response was invalid.")
        return data

    container.dashboard_launcher = launch_dashboard
    return container


async def call_local_tool(
    settings: GlobalMemorySettings,
    paths: PlatformPaths,
    *,
    endpoint: str,
    token_file: Path,
    name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Invoke the frozen MCP contract through an in-memory local transport."""
    container = build_local_container(settings, paths, endpoint=endpoint, token_file=token_file)
    try:
        async with create_connected_server_and_client_session(create_mcp_server(container)) as session:
            result = await session.call_tool(name, arguments)
        envelope = result.structuredContent
        if not isinstance(envelope, dict):
            raise GlobalMemoryError(
                ErrorCode.INTERNAL_ERROR,
                "The local MCP runtime returned no structured V1 envelope.",
            )
        return envelope
    finally:
        container.database.close()


async def call_runtime_tool(
    endpoint: str,
    token_file: Path,
    name: str,
    arguments: dict[str, Any],
    *,
    config_file: Path | None = None,
    paths: PlatformPaths | None = None,
) -> dict[str, Any]:
    """Prefer a ready shared daemon, otherwise execute the same MCP contract locally."""
    if await daemon_ready(endpoint):
        return await call_http_tool(endpoint, token_file, name, arguments)
    selected_paths = paths or get_platform_paths()
    settings = load_settings(config_file or selected_paths.config_file)
    return await call_local_tool(
        settings,
        selected_paths,
        endpoint=endpoint,
        token_file=token_file,
        name=name,
        arguments=arguments,
    )


async def serve_local_stdio(
    settings: GlobalMemorySettings,
    paths: PlatformPaths,
    *,
    endpoint: str,
    token_file: Path,
) -> None:
    """Serve the complete MCP contract over stdio without an HTTP daemon."""
    from mcp.server.stdio import stdio_server

    container = build_local_container(settings, paths, endpoint=endpoint, token_file=token_file)
    server = create_mcp_server(container)
    try:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options(),
                raise_exceptions=False,
            )
    finally:
        container.database.close()
