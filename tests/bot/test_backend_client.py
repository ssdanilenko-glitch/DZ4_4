import httpx
import pytest
from uuid import UUID

from bot.services.backend_client import BackendClient

FAKE_CHAT_ID = "123e4567-e89b-12d3-a456-426614174000"


@pytest.mark.asyncio
async def test_send_message_parses_json_sse():
    def handler(request: httpx.Request) -> httpx.Response:
        body = (
            b'data: {"type":"token","delta":"Hello"}\n\n'
            b'data: {"type":"token","delta":" world"}\n\n'
            b'data: {"type":"done"}\n\n'
        )
        return httpx.Response(200, content=body, headers={"Content-Type": "text/event-stream"})

    client = BackendClient()
    client._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    tokens = [t async for t in client.send_message(UUID(FAKE_CHAT_ID), "hi")]
    assert tokens == ["Hello", " world"]
    await client.close()


@pytest.mark.asyncio
async def test_send_message_with_media_is_multipart():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["content-type"].startswith("multipart/form-data")
        body = b'data: {"type":"token","delta":"ok"}\n\ndata: {"type":"done"}\n\n'
        return httpx.Response(200, content=body, headers={"Content-Type": "text/event-stream"})

    client = BackendClient()
    client._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    tokens = [t async for t in client.send_message(
        UUID(FAKE_CHAT_ID), "что на фото?", media=b"\x89PNG...", mime="image/png"
    )]
    assert tokens == ["ok"]
    await client.close()