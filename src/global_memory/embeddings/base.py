"""Embedding provider port."""

from __future__ import annotations

from typing import Protocol


class EmbeddingProvider(Protocol):
    provider: str
    model: str
    dimension: int | None

    def embed(self, texts: list[str]) -> list[list[float]]: ...
