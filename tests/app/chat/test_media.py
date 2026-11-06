import pytest
from io import BytesIO
from fastapi import UploadFile
from starlette.datastructures import Headers

from app.chat.media import media_to_part


@pytest.mark.asyncio
async def test_pdf_returns_text_part():
    # минимальный валидный PDF можно сгенерировать pypdf или взять фикстуру
    # здесь — заглушка, подставьте реальный PDF-байт
    ...


@pytest.mark.asyncio
async def test_image_returns_image_url_part():
    png = b"\x89PNG\r\n\x1a\n..."  # валидный PNG
    upload = UploadFile(
        file=BytesIO(png),
        filename="x.png",
        headers=Headers({"content-type": "image/png"}),
    )
    part = await media_to_part(upload)
    assert part["type"] == "image_url"
    assert part["image_url"]["url"].startswith("data:image/png;base64,")