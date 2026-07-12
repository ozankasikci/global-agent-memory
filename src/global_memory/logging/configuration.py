"""Structured content-free logging with recursive redaction."""

from __future__ import annotations

import re
import sys
from collections.abc import MutableMapping
from typing import Any, TextIO, cast

import structlog

SENSITIVE_KEYS = re.compile(r"(?i)(content|body|prompt|embedding|secret|token|password|authorization)")
SENSITIVE_TEXT = re.compile(r"(?i)(Bearer\s+)[A-Za-z0-9._~+/-]{8,}=*|\bsk-(?:proj-)?[A-Za-z0-9_-]{12,}\b")
REDACTED = "[REDACTED]"


def _redact(value: Any, key: str = "") -> Any:
    if SENSITIVE_KEYS.search(key):
        return REDACTED
    if isinstance(value, dict):
        return {str(item_key): _redact(item, str(item_key)) for item_key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in value]
    if isinstance(value, str):
        return SENSITIVE_TEXT.sub(REDACTED, value)
    return value


def redact_event(_logger: Any, _method_name: str, event_dict: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    """Structlog processor that never emits known sensitive fields or token shapes."""
    return cast(MutableMapping[str, Any], _redact(dict(event_dict)))


def configure_logging(*, stream: TextIO | None = None) -> None:
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            redact_event,
            structlog.processors.JSONRenderer(sort_keys=True),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=stream or sys.stderr),
        cache_logger_on_first_use=False,
    )


def get_logger() -> Any:
    return structlog.get_logger("global_memory")
