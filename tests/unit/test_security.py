from __future__ import annotations

import io
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from global_memory.errors import ErrorCode, GlobalMemoryError
from global_memory.logging import configure_logging, get_logger
from global_memory.mcp.daemon import run_daemon
from global_memory.security import reject_probable_secrets
from global_memory.vault.paths import safe_vault_path


@pytest.mark.parametrize(
    "secret",
    [
        "-----BEGIN PRIVATE KEY-----",
        "sk-proj-abcdefghijklmnopqrstuvwxyz123456",
        "AKIAABCDEFGHIJKLMNOP",
        "password=correct-horse-battery-staple",
        "Authorization: Bearer abcdefghijklmnopqrstuvwxyz",
    ],
)
def test_probable_secrets_are_rejected_without_echo(secret: str) -> None:
    with pytest.raises(GlobalMemoryError) as caught:
        reject_probable_secrets(secret)
    assert caught.value.code is ErrorCode.NOTE_INVALID
    assert secret not in str(caught.value) and secret not in str(caught.value.details)


def test_structured_log_capture_redacts_fields_and_inline_tokens() -> None:
    stream = io.StringIO()
    configure_logging(stream=stream)
    get_logger().info(
        "request_failed",
        memory_id="mem_safe",
        content="private body",
        nested={"authorization": "Bearer abcdefghijklmnop"},
        reason="received sk-proj-abcdefghijklmnopqrstuvwxyz",
    )
    event = json.loads(stream.getvalue())
    rendered = json.dumps(event)
    assert event["memory_id"] == "mem_safe"
    assert event["content"] == "[REDACTED]"
    assert "private body" not in rendered and "sk-proj" not in rendered and "Bearer" not in rendered


@given(st.text(min_size=1, max_size=100))
def test_traversal_property_never_resolves_outside_vault(raw: str) -> None:
    vault = Path("/tmp/global-memory-security-vault")
    relative = Path(raw)
    try:
        resolved = safe_vault_path(vault, relative).resolve(strict=False)
    except (GlobalMemoryError, ValueError, OSError):
        return
    assert resolved.is_relative_to(vault.resolve())


@pytest.mark.asyncio
async def test_daemon_applies_configured_connection_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    class FakeConfig:
        def __init__(self, app: object, **kwargs: Any) -> None:
            captured.update(kwargs)

    class FakeServer:
        def __init__(self, _config: FakeConfig) -> None:
            pass

        async def serve(self) -> None:
            return None

    token_file = tmp_path / "token"
    token_file.write_text("secret\n")
    monkeypatch.setattr("global_memory.mcp.daemon.create_http_app", lambda **_kwargs: object())
    monkeypatch.setattr("global_memory.mcp.daemon.uvicorn.Config", FakeConfig)
    monkeypatch.setattr("global_memory.mcp.daemon.uvicorn.Server", FakeServer)
    arguments = SimpleNamespace(
        token_file=token_file,
        embedding_provider="none",
        embedding_model="unused",
        embedding_base_url="http://127.0.0.1:11434",
        embedding_batch_size=8,
        embedding_dimension=None,
        vault=tmp_path / "vault",
        state=tmp_path / "state",
        host="127.0.0.1",
        port=9876,
        max_request_bytes=1024,
        max_connections=7,
        instance_id="test",
        no_watch=True,
        debounce_ms=50,
        exclude=[],
    )

    await run_daemon(arguments)

    assert captured["host"] == "127.0.0.1"
    assert captured["limit_concurrency"] == 7
