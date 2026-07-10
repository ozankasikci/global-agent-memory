"""Content safety checks at trust boundaries."""

from __future__ import annotations

import re

from global_memory.errors import ErrorCode, GlobalMemoryError

SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"(?i)\b(?:password|passwd|api[_-]?key|auth[_-]?token)\s*[:=]\s*[^\s]{8,}"),
    re.compile(r"(?i)\bAuthorization:\s*Bearer\s+[A-Za-z0-9._~+/-]{12,}=*"),
)


def reject_probable_secrets(*values: str | None) -> None:
    """Reject likely credentials without returning the matched value."""
    if any(pattern.search(value) for value in values if value for pattern in SECRET_PATTERNS):
        raise GlobalMemoryError(
            ErrorCode.NOTE_INVALID,
            "The memory appears to contain a credential or secret.",
            details={"secret_detected": True},
            remediation="Remove the secret and store only a non-sensitive durable conclusion.",
        )
