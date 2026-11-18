"""
An aiogram session over the Workers fetch(). aiohttp cannot open connections in a Worker: it
tries raw sockets.

encode_form() is plain Python; FetchSession only works inside a Worker.
"""

from __future__ import annotations

import secrets
from collections.abc import AsyncGenerator
from typing import Any, cast
from urllib.parse import urlencode

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.exceptions import TelegramNetworkError
from aiogram.methods import TelegramMethod
from aiogram.methods.base import TelegramType
from aiogram.types import InputFile


def _quote(name: str) -> str:
    # field names are ours; file names too (kuvaaja.png, the /data export), but be safe anyway
    return name.replace("\\", "\\\\").replace('"', '\\"').replace("\r", "").replace("\n", "")


def encode_form(fields: dict[str, str], files: dict[str, tuple[str, bytes]]) -> tuple[bytes, str]:
    """The request body and its content type: urlencoded, or multipart when there are files."""
    if not files:
        return urlencode(fields).encode(), "application/x-www-form-urlencoded"
    boundary = "----kakkosvuohi" + secrets.token_hex(16)
    parts: list[bytes] = []
    for name, value in fields.items():
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{_quote(name)}"\r\n\r\n'.encode()
            + value.encode()
            + b"\r\n"
        )
    for name, (filename, data) in files.items():
        parts.append(
            (
                f"--{boundary}\r\nContent-Disposition: form-data; "
                f'name="{_quote(name)}"; filename="{_quote(filename)}"\r\n'
                "Content-Type: application/octet-stream\r\n\r\n"
            ).encode()
            + data
            + b"\r\n"
        )
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


class FetchSession(BaseSession):
    async def _form(self, bot: Bot, method: TelegramMethod[Any]) -> tuple[bytes, str]:
        fields: dict[str, str] = {}
        inputs: dict[str, InputFile] = {}
        for key, value in method.model_dump(warnings=False).items():
            value = self.prepare_value(value, bot=bot, files=inputs)
            if not value:
                continue
            fields[key] = value if isinstance(value, str) else str(value)
        files = {}
        for key, item in inputs.items():
            data = b"".join([chunk async for chunk in item.read(bot)])
            files[key] = (item.filename or key, data)
        return encode_form(fields, files)

    async def make_request(
        self,
        bot: Bot,
        method: TelegramMethod[TelegramType],
        timeout: int | None = None,  # noqa: ASYNC109 - the signature of BaseSession
    ) -> TelegramType:
        from js import AbortSignal, Object, fetch  # only in a Worker
        from pyodide.ffi import JsException, to_js

        url = self.api.api_url(token=bot.token, method=method.__api_method__)
        body, content_type = await self._form(bot, method)
        seconds = self.timeout if timeout is None else timeout
        options = to_js(
            {
                "method": "POST",
                "headers": {"content-type": content_type},
                "body": to_js(body),
                "signal": AbortSignal.timeout(int(seconds * 1000)),
            },
            dict_converter=Object.fromEntries,
        )
        try:
            resp = await fetch(url, options)
            text = await resp.text()
        except JsException as e:
            # never the url in the message: it contains the bot token
            raise TelegramNetworkError(method=method, message=f"fetch failed: {e.name}") from None
        response = self.check_response(
            bot=bot, method=method, status_code=resp.status, content=text
        )
        return cast(TelegramType, response.result)

    async def stream_content(
        self,
        url: str,
        headers: dict[str, Any] | None = None,
        timeout: int = 30,  # noqa: ASYNC109
        chunk_size: int = 65536,
        raise_for_status: bool = True,
    ) -> AsyncGenerator[bytes, None]:
        """Downloading files: the bot never does, but aiogram requires it."""
        raise NotImplementedError("the bot does not download files")
        yield b""  # pragma: no cover - makes this an async generator

    async def close(self) -> None:
        """fetch() has no connections to close."""
