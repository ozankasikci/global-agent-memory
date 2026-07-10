"""Deterministic fake embeddings for normal tests."""

from __future__ import annotations

import hashlib
import math

from global_memory.errors import ErrorCode, GlobalMemoryError


class FakeEmbeddingProvider:
    provider = "fake"

    def __init__(self, *, model: str = "fake-embedding", dimension: int = 16, available: bool = True) -> None:
        self.model = model
        self.dimension = dimension
        self.available = available
        self.calls: list[list[str]] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not self.available:
            raise GlobalMemoryError(
                ErrorCode.EMBEDDING_PROVIDER_UNAVAILABLE,
                "The fake embedding provider is unavailable.",
                retryable=True,
            )
        self.calls.append(list(texts))
        result: list[list[float]] = []
        for text in texts:
            values: list[float] = []
            counter = 0
            while len(values) < self.dimension:
                digest = hashlib.sha256(f"{counter}:{text}".encode()).digest()
                values.extend((byte - 127.5) / 127.5 for byte in digest)
                counter += 1
            values = values[: self.dimension]
            magnitude = math.sqrt(sum(value * value for value in values)) or 1.0
            result.append([value / magnitude for value in values])
        return result
