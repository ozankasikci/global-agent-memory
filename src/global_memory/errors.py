"""Transport-independent domain and application errors."""

from __future__ import annotations

from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
    """Stable V1 error codes shared by every adapter."""

    CONTRACT_VERSION_UNSUPPORTED = "CONTRACT_VERSION_UNSUPPORTED"
    CONFIG_INVALID = "CONFIG_INVALID"
    VAULT_NOT_FOUND = "VAULT_NOT_FOUND"
    VAULT_NOT_WRITABLE = "VAULT_NOT_WRITABLE"
    NOTE_NOT_FOUND = "NOTE_NOT_FOUND"
    NOTE_INVALID = "NOTE_INVALID"
    DUPLICATE_ID = "DUPLICATE_ID"
    POSSIBLE_DUPLICATE = "POSSIBLE_DUPLICATE"
    REQUEST_ID_CONFLICT = "REQUEST_ID_CONFLICT"
    VERSION_CONFLICT = "VERSION_CONFLICT"
    PATH_OUTSIDE_VAULT = "PATH_OUTSIDE_VAULT"
    PROJECT_NOT_FOUND = "PROJECT_NOT_FOUND"
    EMBEDDING_PROVIDER_UNAVAILABLE = "EMBEDDING_PROVIDER_UNAVAILABLE"
    VECTOR_INDEX_UNAVAILABLE = "VECTOR_INDEX_UNAVAILABLE"
    INDEX_CORRUPT = "INDEX_CORRUPT"
    INDEX_BUSY = "INDEX_BUSY"
    DAEMON_UNAVAILABLE = "DAEMON_UNAVAILABLE"
    UNAUTHORIZED = "UNAUTHORIZED"
    REQUEST_TOO_LARGE = "REQUEST_TOO_LARGE"
    CLIENT_NOT_INSTALLED = "CLIENT_NOT_INSTALLED"
    INTEGRATION_CONFLICT = "INTEGRATION_CONFLICT"
    INTEGRATION_VERIFY_FAILED = "INTEGRATION_VERIFY_FAILED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class GlobalMemoryError(Exception):
    """Safe structured failure independent from MCP transport behavior."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
        remediation: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.details = details or {}
        self.remediation = remediation

    def as_dict(self) -> dict[str, Any]:
        """Return the V1 error payload without transport-specific types."""
        return {
            "code": self.code.value,
            "message": self.message,
            "retryable": self.retryable,
            "details": self.details,
            "remediation": self.remediation,
        }
