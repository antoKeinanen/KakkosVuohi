from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware, Bot
from aiogram.dispatcher.flags import get_flag
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import CommandObject
from aiogram.types import CallbackQuery, Message, TelegramObject

from . import access
from .announcements import ANNOUNCEMENTS
from .config import Settings
from .db import Store
from .formatting import chunk_text
from .strings import S
from .telegram_utils import safe_answer

log = logging.getLogger("blakkis.commands")
Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]


class ThrottleMiddleware(BaseMiddleware):
    """
    Per-user token bucket. A single account must not be able to flood the bot (and, through it,
    the database and the CPU-heavy chart rendering). Updates over the limit are dropped.
    """

    def __init__(
        self, rate: float = 2.0, burst: int = 10, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._rate = rate
        self._burst = burst
        self._clock = clock
        self._buckets: dict[int, tuple[float, float]] = {}  # user id -> (tokens, last update)

    def _allow(self, user_id: int) -> bool:
        now = self._clock()
        tokens, last = self._buckets.get(user_id, (float(self._burst), now))
        tokens = min(float(self._burst), tokens + (now - last) * self._rate)
        allowed = tokens >= 1
        self._buckets[user_id] = (tokens - 1 if allowed else tokens, now)
        if len(self._buckets) > 10_000:  # forget idle users so that memory stays bounded
            self._buckets = {
                uid: b for uid, b in self._buckets.items() if b[0] < self._burst or now - b[1] < 60
            }
        return allowed

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        user = getattr(event, "from_user", None)
        if user is None or user.is_bot:
            return None
        if not self._allow(user.id):
            log.debug("throttled an update")
            if isinstance(event, CallbackQuery):
                await safe_answer(event)
            return None
        return await handler(event, data)


class ForeignCommandMiddleware(BaseMiddleware):
    """Drops '/command@otherbot': it is meant for another bot that shares the chat."""

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        if isinstance(event, Message) and event.text and event.text.startswith("/"):
            first_word = event.text.split(maxsplit=1)[0]
            _, at, mention = first_word.partition("@")
            if at:
                me = await data["bot"].me()
                if mention.lower() != (me.username or "").lower():
                    return None
        return await handler(event, data)


class AccessMiddleware(BaseMiddleware):
    """
    Enforces the `scope` and `privilege` flags of the matched handler, loads the user of the
    update into `data["user"]` and delivers announcements.
    """

    def __init__(self, store: Store, settings: Settings) -> None:
        self._store = store
        self._settings = settings

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        bot: Bot = data["bot"]
        scope = get_flag(data, "scope", default=access.ANYWHERE)
        privilege = get_flag(data, "privilege", default=access.EVERYONE)

        if isinstance(event, Message):
            chat = event.chat
        elif isinstance(event, CallbackQuery) and event.message is not None:
            chat = event.message.chat
        else:
            return None
        tg_user = event.from_user
        if tg_user is None or chat.type == "channel":
            return None
        is_private = chat.type == "private"
        command: CommandObject | None = data.get("command")

        async def deny(text: str) -> None:
            if isinstance(event, CallbackQuery):
                await safe_answer(event, text, show_alert=True)
            else:
                await _send(bot, tg_user.id, text)

        if scope == access.PRIVATE and not is_private:
            # do not nag without a proper @botname suffix in chats
            if command is not None and command.mention:
                await deny(S.commands.blakkis.use_only_in_private)
            return None
        if scope == access.CHAT and is_private:
            await deny(S.commands.blakkis.use_only_in_chats)
            return None

        is_admin = self._settings.admin_id is not None and tg_user.id == self._settings.admin_id
        if privilege == access.ADMIN and not is_admin:
            await deny(S.commands.blakkis.unauthorized)
            return None

        user = await self._store.users.find(tg_user.id)
        if privilege == access.USER:
            if user is None:
                await deny(S.commands.blakkis.user404)
                return None
            if not user.read_terms:
                await deny(S.commands.blakkis.please_update_user_info)
                return None

        if user is not None:
            await self._store.users.touch(user)  # being used keeps the account from expiring
        if user is not None and user.read_announcements < len(ANNOUNCEMENTS):
            await self._deliver_announcements(bot, tg_user.id, user)

        if command is not None and "state" in data:
            # a command always interrupts whatever the user was in the middle of
            await data["state"].clear()

        data["user"] = user
        data["is_admin"] = is_admin
        return await handler(event, data)

    async def _deliver_announcements(self, bot: Bot, telegram_id: int, user) -> None:  # noqa: ANN001
        unread = ANNOUNCEMENTS[user.read_announcements :]
        first, *rest = chunk_text(unread)
        delivered = await _send(
            bot,
            telegram_id,
            S.commands.blakkis.announcements.format(announcements=first),
            plain=True,
        )
        for text in rest:
            delivered = delivered and await _send(bot, telegram_id, text, plain=True)
        # Only mark them read when they really got through: in a group chat the user may never
        # have started the bot, and then they are shown at their next private message.
        if delivered:
            await self._store.users.update_read_announcements(user, len(ANNOUNCEMENTS))


async def _send(bot: Bot, chat_id: int, text: str, *, plain: bool = False) -> bool:
    try:
        if plain:  # static text that is not HTML: show it exactly as it is
            await bot.send_message(chat_id, text, parse_mode=None)
        else:
            await bot.send_message(chat_id, text)
        return True
    except TelegramAPIError as exc:
        log.info("Could not send a message privately: %s", exc)
        return False
