"""Opaque snapshot-bound keyset cursors."""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import asdict, dataclass

from global_memory.errors import ErrorCode, GlobalMemoryError


@dataclass(frozen=True, slots=True)
class CursorKey:
    snapshot: str
    score: float
    updated_at: str
    memory_id: str


def encode_cursor(key: CursorKey) -> str:
    payload = json.dumps(asdict(key), sort_keys=True, separators=(",", ":")).encode()
    signature = hashlib.sha256(b"global-memory-v1-cursor:" + payload).hexdigest()[:16].encode()
    return base64.urlsafe_b64encode(signature + b"." + payload).decode().rstrip("=")


def decode_cursor(value: str, *, expected_snapshot: str) -> CursorKey:
    try:
        padded = value + "=" * (-len(value) % 4)
        signature, payload = base64.urlsafe_b64decode(padded.encode()).split(b".", 1)
        expected = hashlib.sha256(b"global-memory-v1-cursor:" + payload).hexdigest()[:16].encode()
        if signature != expected:
            raise ValueError("cursor signature mismatch")
        key = CursorKey(**json.loads(payload))
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise GlobalMemoryError(
            ErrorCode.NOTE_INVALID,
            "The search cursor is invalid.",
            details={},
            remediation="Restart pagination without a cursor.",
        ) from exc
    if key.snapshot != expected_snapshot:
        raise GlobalMemoryError(
            ErrorCode.VERSION_CONFLICT,
            "The search index changed after this cursor was issued.",
            details={},
            remediation="Restart pagination to use the current index snapshot.",
        )
    return key
