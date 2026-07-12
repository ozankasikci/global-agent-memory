from __future__ import annotations

import anyio
import pytest
from mcp import types
from mcp.shared.message import SessionMessage

from global_memory.mcp.stdio_proxy import _pump


@pytest.mark.asyncio
async def test_proxy_pump_preserves_cancellation_message_identity() -> None:
    source_send, source_receive = anyio.create_memory_object_stream[SessionMessage | Exception](1)
    destination_send, destination_receive = anyio.create_memory_object_stream[SessionMessage](1)
    cancellation = SessionMessage(
        types.CancelledNotification(params=types.CancelledNotificationParams(requestId="request-42"))
    )

    async with source_send, source_receive, destination_send, destination_receive:
        await source_send.send(cancellation)
        await source_send.aclose()
        await _pump(source_receive, destination_send)

        forwarded = await destination_receive.receive()
        assert forwarded is cancellation


@pytest.mark.asyncio
async def test_proxy_pump_preserves_transport_errors() -> None:
    source_send, source_receive = anyio.create_memory_object_stream[SessionMessage | Exception](1)
    destination_send, destination_receive = anyio.create_memory_object_stream[SessionMessage](1)
    failure = RuntimeError("transport failed")

    async with source_send, source_receive, destination_send, destination_receive:
        await source_send.send(failure)
        await source_send.aclose()

        with pytest.raises(RuntimeError, match="transport failed") as caught:
            await _pump(source_receive, destination_send)
        assert caught.value is failure
