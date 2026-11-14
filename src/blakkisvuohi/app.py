"""Assembling and running the bot."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
import time

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError
from aiogram.fsm.storage.base import BaseEventIsolation, BaseStorage
from aiogram.fsm.storage.memory import MemoryStorage, SimpleEventIsolation
from aiogram.types import ErrorEvent
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from . import __version__
from .config import Settings
from .db import RetentionPolicy, Store
from .formatting import esc
from .handlers import build_routers
from .middlewares import AccessMiddleware, ForeignCommandMiddleware, ThrottleMiddleware
from .scheduler import purge_forever
from .security import Crypto
from .strings import S

log = logging.getLogger("blakkis.system")

# The bot only ever needs these: everything else Telegram could send is not even delivered
ALLOWED_UPDATES = ["message", "callback_query"]


def build_dispatcher(
    store: Store,
    settings: Settings,
    *,
    storage: BaseStorage | None = None,
    events_isolation: BaseEventIsolation | None = None,
    throttle: ThrottleMiddleware | None = None,
) -> Dispatcher:
    dp = Dispatcher(
        # Conversation state (the half-finished /juoma etc.) lives in memory, as it always did
        storage=storage or MemoryStorage(),
        # one update of a user at a time, so quick button presses cannot race each other
        events_isolation=events_isolation or SimpleEventIsolation(),
        store=store,
        settings=settings,
    )
    throttle = throttle or ThrottleMiddleware()
    access = AccessMiddleware(store, settings)
    dp.message.outer_middleware(ForeignCommandMiddleware())
    for observer in (dp.message, dp.callback_query):
        observer.outer_middleware(throttle)  # before anything costs anything
        observer.middleware(access)  # after the handler was matched: needs its flags
    dp.errors.register(_on_error)
    for router in build_routers():
        dp.include_router(router)
    return dp


_last_admin_notice = 0.0


async def _on_error(event: ErrorEvent, bot: Bot, settings: Settings) -> bool:
    global _last_admin_notice  # noqa: PLW0603
    exc = event.exception
    if isinstance(exc, TelegramForbiddenError):
        log.info("A user has blocked the bot or kicked it from a chat")
        return True
    log.error("Unhandled error", exc_info=exc)

    update = event.update
    message = update.message
    callback = update.callback_query
    tg_user = (message or callback).from_user if (message or callback) else None
    chat_id = tg_user.id if tg_user else None

    if chat_id is not None:
        try:
            await bot.send_message(chat_id, S.commands.blakkis.error)
        except TelegramAPIError:
            log.warning("Could not tell the user about an error")
    # Tell the admin, but not too often, and never with the contents of the user's message
    now = time.monotonic()
    if settings.admin_id and now - _last_admin_notice > 10:
        _last_admin_notice = now
        what = (message.text or "").split()[0] if message and message.text else "(non-command)"
        try:
            await bot.send_message(
                settings.admin_id,
                f"Unknown error {esc(type(exc).__name__)}: {esc(str(exc)[:200])}\n"
                f"update {update.update_id}, input: {esc(what[:50])}",
            )
        except TelegramAPIError:
            log.warning("Could not tell the admin about an error")
    return True


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=level, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s", force=True
    )
    # aiogram logs whole updates (that is: users' messages) at DEBUG. Never do that.
    logging.getLogger("aiogram.event").setLevel(max(logging.INFO, logging.getLogger().level))


async def run(settings: Settings) -> None:
    crypto = Crypto(settings.secret_key.get_secret_value())
    store = await Store.open(
        settings.database_path,
        settings.key_database_path,
        crypto,
        policy=RetentionPolicy(settings.retention_days, settings.account_days),
    )
    bot = Bot(
        token=settings.bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = build_dispatcher(store, settings)
    log.info("KakkosVuohi %s started in %s mode", __version__, settings.bot_mode)
    purge = asyncio.create_task(
        purge_forever(store, settings.purge_hour, settings.tzinfo), name="purge"
    )
    try:
        if settings.bot_mode == "polling":
            # a webhook that is still registered would make polling fail
            await bot.delete_webhook()
            await dp.start_polling(bot, allowed_updates=ALLOWED_UPDATES)
        else:
            await _run_webhook(bot, dp, settings, crypto)
    finally:
        purge.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await purge
        await bot.session.close()
        await store.close()


def create_webhook_app(bot: Bot, dp: Dispatcher, *, path: str, secret: str) -> web.Application:
    app = web.Application()

    async def healthz(request: web.Request) -> web.Response:
        return web.json_response({"status": "ok"})

    app.router.add_get("/healthz", healthz)
    # Telegram proves that a request is really from it with the secret token header
    SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=secret).register(app, path=path)
    setup_application(app, dp, bot=bot)
    return app


async def _run_webhook(bot: Bot, dp: Dispatcher, settings: Settings, crypto: Crypto) -> None:
    assert settings.webhook_url and settings.webhook_secret
    path = crypto.webhook_path()
    secret = settings.webhook_secret.get_secret_value()

    # no access log: it would write the secret webhook path into the logs
    runner = web.AppRunner(create_webhook_app(bot, dp, path=path, secret=secret), access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, settings.host, settings.port)
    await site.start()
    await bot.set_webhook(
        settings.webhook_url.rstrip("/") + path,
        secret_token=secret,
        allowed_updates=ALLOWED_UPDATES,
    )
    log.info("Web server listening on %s:%s", settings.host, settings.port)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    try:
        await stop.wait()
    finally:
        await runner.cleanup()
