"""Content safety checks for untrusted memory input."""

from .secrets import reject_probable_secrets

__all__ = ["reject_probable_secrets"]
