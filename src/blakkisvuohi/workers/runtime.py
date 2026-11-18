"""
The bot as a Worker: built once per isolate, then a webhook request or a Cron Trigger at a time.
Plain Python: the JavaScript side (src/worker.py) hands in the configuration, the D1 clients and
the session.

Telegram is told to send one update at a time (max_connections=1), so that updates are handled in
order, as in the long running bot. A request returns when its update has been handled. An update
is handled at most once: Telegram sends it again if the Worker failed (or was too slow), and a
second /kalja033 must not record a second drink, nor must an update that crashes the Worker block
all the others.
"""

from __future__ import annotations

import hmac
import json
import logging
import sys
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.base import BaseSession
from aiogram.enums import ParseMode

from ..app import ALLOWED_UPDATES, build_dispatcher, configure_logging
from ..config import Settings
from ..conversations import DatabaseStorage
from ..db import D1Database, RetentionPolicy, Store
from ..db.d1 import D1Client
from ..db.database import DATA_MIGRATIONS, KEY_MIGRATIONS
from ..scheduler import purge_on_schedule
from ..security import Crypto

log = logging.getLogger("blakkis.system")

SECRET_HEADER = "x-telegram-bot-api-secret-token"  # noqa: S105 - a header name

# Telegram numbers updates in order, but picks a random number after a week without updates
REPEAT_WINDOW = 6 * 24 * 3600


def settings_from(env: Mapping[str, Any]) -> Settings:
    """The settings from the Worker's variables and secrets (BOT_TOKEN, SECRET_KEY...)."""
    values = {
        name: env[name.upper()]
        for name in Settings.model_fields
        if env.get(name.upper()) not in (None, "")
    }
    values["bot_mode"] = "worker"
    return Settings(_env_file=None, _secrets_dir=None, **values)  # type: ignore[call-arg]


@dataclass
class Runtime:
    settings: Settings
    store: Store
    bot: Bot
    dp: Dispatcher
    webhook_path: str

    @property
    def secret(self) -> str:
        assert self.settings.webhook_secret  # required in worker mode
        return self.settings.webhook_secret.get_secret_value()


async def build(
    settings: Settings, data: D1Client, keys: D1Client, session: BaseSession
) -> Runtime:
    # stdout: Workers show everything written to stderr as an error
    configure_logging(settings.log_level, sys.stdout)
    crypto = Crypto(settings.secret_key.get_secret_value())
    store = await Store.from_databases(
        await D1Database.open(data, DATA_MIGRATIONS),
        await D1Database.open(keys, KEY_MIGRATIONS),
        crypto,
        policy=RetentionPolicy(settings.retention_days, settings.account_days),
    )
    bot = Bot(
        token=settings.bot_token.get_secret_value(),
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    # conversations must outlive the isolate: in the database, not in memory
    dp = build_dispatcher(store, settings, storage=DatabaseStorage(store.db, store.vault, crypto))
    return Runtime(settings, store, bot, dp, crypto.webhook_path())


async def _first_delivery(rt: Runtime, update_id: int, now: float) -> bool:
    """Records the update as handled; False if it already was (Telegram sent it again)."""
    db = rt.store.db
    row = await db.fetchone("SELECT value FROM meta WHERE key = 'last_update'")
    if row is not None:
        last_id, at = json.loads(row["value"])
        if update_id <= last_id and now - at < REPEAT_WINDOW:
            return False
    await db.execute(
        "INSERT INTO meta (key, value) VALUES ('last_update', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (json.dumps([update_id, now]),),
    )
    return True


def _authorised(given: str | None, secret: str) -> bool:
    return hmac.compare_digest((given or "").encode(), secret.encode())


async def handle_request(
    rt: Runtime,
    method: str,
    path: str,
    headers: Mapping[str, str],
    body: str,
    origin: str,
    clock: Callable[[], float] = time.time,
) -> tuple[int, str]:
    """Status and JSON body. `headers` have lower case names; `origin` is e.g. https://x.dev"""
    if method == "GET" and path == "/healthz":
        return 200, '{"status":"ok"}'

    if method == "POST" and path == rt.webhook_path:
        # Telegram proves that a request is really from it with the secret token header
        if not _authorised(headers.get(SECRET_HEADER), rt.secret):
            return 401, '{"error":"unauthorized"}'
        try:
            update = json.loads(body)
        except ValueError:
            return 400, '{"error":"bad request"}'
        if not isinstance(update, dict) or not isinstance(update.get("update_id"), int):
            return 400, '{"error":"bad request"}'
        if not await _first_delivery(rt, update["update_id"], clock()):
            log.info("Update %d was already handled", update["update_id"])
            return 200, "{}"
        await rt.dp.feed_raw_update(rt.bot, update)
        return 200, "{}"

    if method == "POST" and path == "/setup-webhook":
        # Once after deploying: points Telegram at this Worker
        authorization = headers.get("authorization", "")
        token = authorization[7:] if authorization.startswith("Bearer ") else None
        if not _authorised(token, rt.secret):
            return 401, '{"error":"unauthorized"}'
        await rt.bot.set_webhook(
            origin + rt.webhook_path,
            secret_token=rt.secret,
            allowed_updates=ALLOWED_UPDATES,
            max_connections=1,
        )
        log.info("Webhook registered")
        return 200, '{"ok":true}'

    return 404, '{"error":"not found"}'


async def handle_scheduled(rt: Runtime) -> None:
    """The hourly Cron Trigger."""
    await purge_on_schedule(rt.store, rt.settings.purge_hour, rt.settings.tzinfo)
