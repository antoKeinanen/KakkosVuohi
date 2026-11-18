"""
The Cloudflare Workers entry point (see wrangler.jsonc). Translates between the Workers runtime
and blakkisvuohi.workers.runtime, which does the work.
"""

from __future__ import annotations

import asyncio
from urllib.parse import urlsplit

from workers import Response, WorkerEntrypoint

from blakkisvuohi.config import Settings
from blakkisvuohi.workers import runtime
from blakkisvuohi.workers.d1 import JsD1Client
from blakkisvuohi.workers.session import FetchSession

_runtime: runtime.Runtime | None = None
_building = asyncio.Lock()


async def _get(env) -> runtime.Runtime:  # the JavaScript env object
    """One bot per isolate. A failed start is not kept: the next request tries again."""
    global _runtime  # noqa: PLW0603
    async with _building:
        if _runtime is None:
            names = [name.upper() for name in Settings.model_fields]
            settings = runtime.settings_from({n: getattr(env, n, None) for n in names})
            if settings.telegram_api_url:
                from aiogram.client.telegram import TelegramAPIServer

                session = FetchSession(api=TelegramAPIServer.from_base(settings.telegram_api_url))
            else:
                session = FetchSession()
            _runtime = await runtime.build(
                settings, JsD1Client(env.DB), JsD1Client(env.KEYS), session
            )
        return _runtime


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        rt = await _get(self.env)
        url = urlsplit(request.url)
        headers = {
            name: request.headers.get(name)
            for name in (runtime.SECRET_HEADER, "authorization")
            if request.headers.get(name) is not None
        }
        body = await request.text() if request.method == "POST" else ""
        status, text = await runtime.handle_request(
            rt, request.method, url.path, headers, body, f"{url.scheme}://{url.netloc}"
        )
        return Response(text, status=status, headers={"content-type": "application/json"})

    async def scheduled(self, controller, env, ctx):
        await runtime.handle_scheduled(await _get(self.env))
