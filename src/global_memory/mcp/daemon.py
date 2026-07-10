"""Authenticated localhost Streamable HTTP daemon for the MCP application."""

from __future__ import annotations

import argparse
import asyncio
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, cast

import uvicorn
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from global_memory.embeddings.base import EmbeddingProvider
from global_memory.embeddings.fake import FakeEmbeddingProvider
from global_memory.embeddings.ollama import OllamaEmbeddingProvider
from global_memory.errors import ErrorCode, GlobalMemoryError
from global_memory.index.watcher import VaultWatcher
from global_memory.logging import configure_logging, get_logger

from .contract import failure
from .server import build_container, create_mcp_server

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_MAX_REQUEST_BYTES = 1_048_576
DEFAULT_MAX_CONNECTIONS = 64


def _error_response(error: GlobalMemoryError, status_code: int) -> JSONResponse:
    return JSONResponse(failure(error), status_code=status_code)


class LocalSecurityMiddleware:
    """Enforce bearer authentication and bounded MCP request bodies."""

    def __init__(self, app: ASGIApp, *, token: str, max_request_bytes: int) -> None:
        self.app = app
        self.token = token
        self.max_request_bytes = max_request_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not str(scope.get("path", "")).startswith("/mcp"):
            await self.app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        supplied = headers.get(b"authorization", b"").decode("latin-1")
        expected = f"Bearer {self.token}"
        if not secrets.compare_digest(supplied, expected):
            response = _error_response(
                GlobalMemoryError(
                    ErrorCode.UNAUTHORIZED,
                    "A valid local daemon bearer token is required.",
                    remediation="Read the protected token file configured for this daemon.",
                ),
                401,
            )
            await response(scope, receive, send)
            return

        content_length = headers.get(b"content-length")
        if content_length is not None:
            try:
                too_large = int(content_length) > self.max_request_bytes
            except ValueError:
                too_large = True
            if too_large:
                await self._too_large(scope, receive, send)
                return

        consumed = 0

        async def bounded_receive() -> Message:
            nonlocal consumed
            message = await receive()
            if message["type"] == "http.request":
                consumed += len(message.get("body", b""))
                if consumed > self.max_request_bytes:
                    raise _RequestTooLarge
            return message

        try:
            await self.app(scope, bounded_receive, send)
        except _RequestTooLarge:
            await self._too_large(scope, receive, send)

    async def _too_large(self, scope: Scope, receive: Receive, send: Send) -> None:
        response = _error_response(
            GlobalMemoryError(
                ErrorCode.REQUEST_TOO_LARGE,
                "The MCP request exceeds the configured local size limit.",
                details={"max_request_bytes": self.max_request_bytes},
                remediation="Send a smaller request or increase mcp.max_request_bytes.",
            ),
            413,
        )
        await response(scope, receive, send)


class _RequestTooLarge(Exception):
    pass


def read_token(path: Path) -> str:
    """Read a non-empty token without ever returning it in an error."""
    try:
        token = path.read_text().strip()
    except OSError as exc:
        raise GlobalMemoryError(
            ErrorCode.CONFIG_INVALID,
            "The daemon token file cannot be read.",
            details={"path": str(path)},
            remediation="Run `global-memory init` or provide a readable --token-file.",
        ) from exc
    if not token:
        raise GlobalMemoryError(ErrorCode.CONFIG_INVALID, "The daemon token file is empty.")
    return token


def create_http_app(
    *,
    vault_path: Path,
    state_path: Path,
    token: str,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    max_request_bytes: int = DEFAULT_MAX_REQUEST_BYTES,
    instance_id: str | None = None,
    watch: bool = True,
    debounce_ms: int = 500,
    excluded_globs: list[str] | None = None,
    embedding_provider: EmbeddingProvider | None = None,
    embedding_batch_size: int = 32,
) -> ASGIApp:
    """Create the minimal authenticated MCP + health ASGI application."""
    container = build_container(
        vault_path,
        state_path,
        transport="streamable-http",
        embedding_provider=embedding_provider,
        embedding_batch_size=embedding_batch_size,
    )
    mcp_server = create_mcp_server(container)
    watcher = VaultWatcher(
        vault_path,
        container.index_jobs,
        debounce_ms=debounce_ms,
        excluded_globs=excluded_globs,
    )
    allowed_hosts = [f"{host}:{port}", f"localhost:{port}", host, "localhost"]
    allowed_origins = [f"http://{host}:{port}", f"http://localhost:{port}"]
    manager = StreamableHTTPSessionManager(
        mcp_server,
        json_response=True,
        stateless=False,
        security_settings=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=allowed_hosts,
            allowed_origins=allowed_origins,
        ),
        session_idle_timeout=1800,
    )

    async def live(_request: Any) -> JSONResponse:
        return JSONResponse({"status": "live", "instance_id": instance_id})

    async def ready(_request: Any) -> JSONResponse:
        return JSONResponse({"status": "ready", "instance_id": instance_id})

    @asynccontextmanager
    async def lifespan(_app: Starlette) -> AsyncIterator[None]:
        if watch:
            watcher.start()
            container.watcher_state = "running"
        try:
            async with manager.run():
                yield
        finally:
            if watch:
                container.watcher_state = "stopping"
                await watcher.stop()
                container.watcher_state = "stopped"

    app = Starlette(
        routes=[
            Route("/health/live", live, methods=["GET"]),
            Route("/health/ready", ready, methods=["GET"]),
            Mount("/mcp", app=manager.handle_request),
        ],
        lifespan=lifespan,
    )
    return LocalSecurityMiddleware(app, token=token, max_request_bytes=max_request_bytes)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Global Memory Streamable HTTP daemon.")
    parser.add_argument("--vault", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument("--host", choices=[DEFAULT_HOST], default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--max-request-bytes", type=int, default=DEFAULT_MAX_REQUEST_BYTES)
    parser.add_argument("--max-connections", type=int, default=DEFAULT_MAX_CONNECTIONS)
    parser.add_argument("--instance-id")
    parser.add_argument("--no-watch", action="store_true")
    parser.add_argument("--debounce-ms", type=int, default=500)
    parser.add_argument("--exclude", action="append", default=[])
    parser.add_argument("--embedding-provider", choices=["none", "ollama", "fake"], default="none")
    parser.add_argument("--embedding-base-url", default="http://127.0.0.1:11434")
    parser.add_argument("--embedding-model", default="nomic-embed-text")
    parser.add_argument("--embedding-dimension", type=int)
    parser.add_argument("--embedding-batch-size", type=int, default=32)
    return parser


async def run_daemon(args: argparse.Namespace) -> None:
    configure_logging()
    logger = get_logger()
    token = read_token(args.token_file)
    embedding_provider: EmbeddingProvider | None = None
    if args.embedding_provider == "ollama":
        embedding_provider = OllamaEmbeddingProvider(
            model=args.embedding_model,
            base_url=args.embedding_base_url,
            batch_size=args.embedding_batch_size,
            dimension=args.embedding_dimension,
            timeout=1.0,
            max_retries=0,
        )
    elif args.embedding_provider == "fake":
        embedding_provider = cast(
            EmbeddingProvider,
            FakeEmbeddingProvider(
                model=args.embedding_model,
                dimension=args.embedding_dimension or 16,
            ),
        )
    app = create_http_app(
        vault_path=args.vault,
        state_path=args.state,
        token=token,
        host=args.host,
        port=args.port,
        max_request_bytes=args.max_request_bytes,
        instance_id=args.instance_id,
        watch=not args.no_watch,
        debounce_ms=args.debounce_ms,
        excluded_globs=args.exclude,
        embedding_provider=embedding_provider,
        embedding_batch_size=args.embedding_batch_size,
    )
    config = uvicorn.Config(
        app,
        host=args.host,
        port=args.port,
        log_level="info",
        access_log=False,
        limit_concurrency=args.max_connections,
    )
    logger.info("daemon_starting", host=args.host, port=args.port)
    try:
        await uvicorn.Server(config).serve()
    finally:
        logger.info("daemon_stopped", host=args.host, port=args.port)


def main() -> None:
    """Console-script entry point."""
    args = _parser().parse_args()
    try:
        asyncio.run(run_daemon(args))
    except GlobalMemoryError as exc:
        raise SystemExit(f"{exc.code.value}: {exc.message}") from exc


if __name__ == "__main__":
    main()
