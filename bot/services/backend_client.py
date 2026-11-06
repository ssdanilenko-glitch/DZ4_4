import json
from typing import AsyncIterator
from uuid import UUID

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from bot.config import settings


class BackendError(Exception):
    pass


class BackendClient:
    def __init__(self):
        self.base_url = settings.BACKEND_URL.rstrip("/")
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=3.0, read=60.0, write=10.0, pool=5.0),
        )

    async def close(self):
        await self._http.aclose()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, max=2),
        retry=retry_if_exception_type((httpx.ConnectError, httpx.ConnectTimeout)),
        reraise=True,
    )
    async def get_or_create_chat(
        self, owner_external_id: str, interface: str = "telegram"
    ) -> UUID:
        resp = await self._http.post(
            f"{self.base_url}/chats",
            json={"owner_external_id": owner_external_id, "interface": interface},
        )
        resp.raise_for_status()
        data = resp.json()
        raw = data.get("chat_id") or data.get("id") or data.get("uuid")
        if not raw:
            raise BackendError(f"Unexpected POST /chats response: {data!r}")
        return UUID(str(raw))

    async def send_message(
            self,
            chat_id: UUID,
            content: str,
            media: bytes | None = None,
            mime: str | None = None,
    ) -> AsyncIterator[str]:
        files = {"media": ("file.bin", media, mime)} if media else None
        data = {"content": content}

        async with self._http.stream(
                "POST",
                f"{self.base_url}/chats/{chat_id}/messages",
                data=data,
                files=files,
                timeout=httpx.Timeout(connect=3.0, read=120.0, write=10.0, pool=5.0),
        ) as resp:
            if resp.status_code >= 400:
                # читаем тело, чтобы raise_for_status дал доступ к нему
                await resp.aread()
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                payload = line[len("data: "):].strip()
                if not payload:
                    continue
                try:
                    obj = json.loads(payload)
                except json.JSONDecodeError:
                    continue

                if not isinstance(obj, dict):
                    continue

                typ = obj.get("type")
                if typ == "token":
                    delta = obj.get("delta", "")
                    if delta:
                        yield delta
                elif typ == "done":
                    return
                elif typ == "error":
                    # backend вернул error-фрейм (например, выходная модерация)
                    code = obj.get("code", "error")
                    msg = obj.get("message") or obj.get("code") or "Ошибка на стороне backend"
                    raise BackendError(f"{code}: {msg}")
                elif "delta" in obj:  # fallback для Б4.2 (сырой формат)
                    yield obj["delta"]

    async def clear_messages(self, chat_id: UUID) -> None:
        resp = await self._http.delete(
            f"{self.base_url}/chats/{chat_id}/messages"
        )
        resp.raise_for_status()