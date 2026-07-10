"""Bounded, retrying adapter for Ollama's current batched embedding API."""

from __future__ import annotations

import time
from collections.abc import Callable

import httpx

from global_memory.errors import ErrorCode, GlobalMemoryError


class OllamaEmbeddingProvider:
    provider = "ollama"

    def __init__(
        self,
        *,
        model: str,
        base_url: str = "http://127.0.0.1:11434",
        batch_size: int = 32,
        timeout: float = 30.0,
        max_retries: int = 2,
        dimension: int | None = None,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.dimension = dimension
        self._client = client or httpx.Client(timeout=timeout)
        self._sleep = sleep

    def _batch(self, texts: list[str]) -> list[list[float]]:
        last_reason = "unknown transport failure"
        for attempt in range(self.max_retries + 1):
            try:
                request = {"model": self.model, "input": texts, "truncate": True}
                if self.dimension is not None:
                    request["dimensions"] = self.dimension
                response = self._client.post(f"{self.base_url}/api/embed", json=request)
                response.raise_for_status()
                payload = response.json()
                embeddings = payload.get("embeddings")
                if not isinstance(embeddings, list) or len(embeddings) != len(texts):
                    raise ValueError("response embedding count does not match the request")
                vectors = [[float(value) for value in vector] for vector in embeddings]
                if not vectors or any(not vector or len(vector) != len(vectors[0]) for vector in vectors):
                    raise ValueError("response vectors have inconsistent dimensions")
                return vectors
            except (httpx.HTTPError, ValueError, TypeError) as exc:
                last_reason = type(exc).__name__
                if attempt < self.max_retries:
                    self._sleep(min(0.25 * (2**attempt), 2.0))
        raise GlobalMemoryError(
            ErrorCode.EMBEDDING_PROVIDER_UNAVAILABLE,
            "The local Ollama embedding provider is unavailable or returned an invalid response.",
            retryable=True,
            details={"provider": self.provider, "model": self.model, "reason": last_reason},
            remediation="Start Ollama and ensure the configured embedding model is installed, or use keyword mode.",
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        result: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            result.extend(self._batch(texts[start : start + self.batch_size]))
        return result
