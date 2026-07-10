from __future__ import annotations

import json

import httpx
import pytest

from global_memory.embeddings.fake import FakeEmbeddingProvider
from global_memory.embeddings.ollama import OllamaEmbeddingProvider
from global_memory.errors import ErrorCode, GlobalMemoryError


def test_fake_embeddings_are_deterministic_normalized_and_configurable() -> None:
    provider = FakeEmbeddingProvider(model="fake-a", dimension=8)
    first = provider.embed(["same", "different"])
    second = provider.embed(["same"])
    assert first[0] == second[0]
    assert first[0] != first[1]
    assert sum(value * value for value in first[0]) == pytest.approx(1.0)
    assert provider.calls == [["same", "different"], ["same"]]


def test_ollama_uses_current_batch_endpoint_and_retries_without_logging_inputs() -> None:
    attempts = 0
    bodies: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        bodies.append(json.loads(request.content))
        if attempts == 1:
            return httpx.Response(503, json={"error": "loading"})
        inputs = bodies[-1]["input"]
        assert isinstance(inputs, list)
        return httpx.Response(200, json={"model": "embed", "embeddings": [[1.0, 0.0] for _ in inputs]})

    provider = OllamaEmbeddingProvider(
        model="embed",
        base_url="http://127.0.0.1:11434",
        batch_size=2,
        max_retries=1,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda _: None,
    )
    result = provider.embed(["secret-one", "secret-two", "secret-three"])
    assert len(result) == 3
    assert attempts == 3
    assert all(body["model"] == "embed" for body in bodies)
    assert all("input" in body for body in bodies)


def test_ollama_outage_has_stable_retryable_error() -> None:
    provider = OllamaEmbeddingProvider(
        model="missing",
        max_retries=1,
        client=httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(503))),
        sleep=lambda _: None,
    )
    with pytest.raises(GlobalMemoryError) as caught:
        provider.embed(["do not expose this"])
    assert caught.value.code is ErrorCode.EMBEDDING_PROVIDER_UNAVAILABLE
    assert caught.value.retryable
    assert "do not expose" not in str(caught.value.details)
