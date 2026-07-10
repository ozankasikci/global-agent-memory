from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from global_memory.errors import ErrorCode, GlobalMemoryError
from global_memory.logging import configure_logging, get_logger
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
