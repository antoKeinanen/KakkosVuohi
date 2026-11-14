"""
Drives the real dispatcher with synthetic Telegram updates. Nothing is sent to Telegram: a fake
session records every API call the bot makes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.base import BaseSession
from aiogram.enums import ParseMode
from aiogram.methods import (
    AnswerCallbackQuery,
    DeleteWebhook,
    EditMessageText,
    GetMe,
    SendDocument,
    SendMessage,
    SendPhoto,
)
from aiogram.types import CallbackQuery, Chat, Message, Update, User

from blakkisvuohi.app import build_dispatcher
from blakkisvuohi.config import Settings
from blakkisvuohi.middlewares import ThrottleMiddleware

BOT_USERNAME = "blakkisvuohibot"


class FakeSession(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.requests: list[Any] = []
        self._next_message_id = 1000
        self.fail_with: dict[int, Exception] = {}  # chat id -> exception to raise when sending

    async def close(self) -> None:  # pragma: no cover
        pass

    async def stream_content(self, *args: Any, **kwargs: Any):  # pragma: no cover
        yield b""

    async def make_request(self, bot: Bot, method: Any, timeout: Any = None) -> Any:  # noqa: ASYNC109
        self.requests.append(method)
        if isinstance(method, GetMe):
            return User(id=42, is_bot=True, first_name="KakkosVuohi", username=BOT_USERNAME)
        if isinstance(method, (DeleteWebhook, AnswerCallbackQuery)):
            return True
        chat_id = getattr(method, "chat_id", None)
        if chat_id in self.fail_with:
            raise self.fail_with[chat_id]
        if isinstance(method, (SendMessage, SendDocument, SendPhoto, EditMessageText)):
            self._next_message_id += 1
            return Message(
                message_id=self._next_message_id,
                date=datetime.now(UTC),
                chat=Chat(id=chat_id or 0, type="private"),
                text=getattr(method, "text", None),
            )
        raise AssertionError(f"unexpected API call {method!r}")


@dataclass
class Sent:
    kind: str  # 'send', 'edit', 'document', 'photo'
    chat_id: int | None
    text: str
    markup: Any
    method: Any

    def buttons(self) -> list[str]:
        markup = self.markup
        rows = getattr(markup, "inline_keyboard", None) or getattr(markup, "keyboard", None) or []
        return [b.text for row in rows for b in row]

    def button_rows(self) -> list[list[str]]:
        markup = self.markup
        rows = getattr(markup, "inline_keyboard", None) or getattr(markup, "keyboard", None) or []
        return [[b.text for b in row] for row in rows]


class Harness:
    def __init__(self, store, settings: Settings, dp: Dispatcher, bot: Bot, session: FakeSession):
        self.store = store
        self.settings = settings
        self.dp = dp
        self.bot = bot
        self.session = session
        self._update_id = 0
        self._cursor = 0
        self.last_bot_message: dict[int, Message] = {}
        self._profiles: dict[
            int, tuple[str | None, str | None]
        ] = {}  # id -> (first name, username)

    # -- sending updates ----------------------------------------------------------------------

    def _tg_user(self, user_id: int, name: str | None = None, username: str | None = None) -> User:
        """Like on Telegram, a user keeps their name and username from message to message."""
        if name is not None or username is not None:
            self._profiles[user_id] = (name, username)
        name, username = self._profiles.get(user_id, (None, None))
        return User(
            id=user_id, is_bot=False, first_name=name or f"User{user_id}", username=username
        )

    async def say(
        self,
        text: str,
        user: int = 1,
        *,
        chat: int | None = None,
        chat_type: str = "private",
        title: str | None = None,
        username: str | None = None,
        first_name: str | None = None,
        is_bot: bool = False,
    ) -> None:
        self._update_id += 1
        chat_id = chat if chat is not None else user
        tg_user = self._tg_user(user, first_name, username)
        if is_bot:
            tg_user = tg_user.model_copy(update={"is_bot": True})
        message = Message(
            message_id=self._update_id,
            date=datetime.now(UTC),
            chat=Chat(id=chat_id, type=chat_type, title=title),
            from_user=tg_user,
            text=text,
        )
        await self.dp.feed_update(self.bot, Update(update_id=self._update_id, message=message))

    async def press(self, button: str, user: int = 1, *, data: str | None = None) -> None:
        """Press a button of the last message the bot sent to the user (or send forged data)."""
        self._update_id += 1
        message = self.last_bot_message.get(user)
        if data is None:
            sent = self.last_with_buttons(user)
            assert sent is not None, "no inline keyboard to press"
            found = [b for row in sent.markup.inline_keyboard for b in row if b.text == button]
            assert found, f"no button {button!r} in {sent.buttons()}"
            data = found[0].callback_data
        callback = CallbackQuery(
            id=str(self._update_id),
            from_user=self._tg_user(user),
            chat_instance="x",
            data=data,
            message=message
            or Message(
                message_id=1,
                date=datetime.now(UTC),
                chat=Chat(id=user, type="private"),
            ),
        )
        await self.dp.feed_update(
            self.bot, Update(update_id=self._update_id, callback_query=callback)
        )

    # -- looking at what the bot did ---------------------------------------------------------

    def _all(self) -> list[Sent]:
        out: list[Sent] = []
        for m in self.session.requests:
            if isinstance(m, SendMessage):
                out.append(Sent("send", m.chat_id, m.text, m.reply_markup, m))
            elif isinstance(m, EditMessageText):
                out.append(Sent("edit", m.chat_id, m.text, m.reply_markup, m))
            elif isinstance(m, SendDocument):
                out.append(Sent("document", m.chat_id, "", None, m))
            elif isinstance(m, SendPhoto):
                out.append(Sent("photo", m.chat_id, m.caption or "", None, m))
        return out

    def new(self) -> list[Sent]:
        """What the bot has sent since the last call."""
        everything = self._all()
        fresh = everything[self._cursor :]
        self._cursor = len(everything)
        for sent in fresh:
            if sent.kind in ("send", "edit") and sent.chat_id is not None:
                self.last_bot_message[sent.chat_id] = Message(
                    message_id=1,
                    date=datetime.now(UTC),
                    chat=Chat(id=sent.chat_id, type="private"),
                    text=sent.text,
                    reply_markup=sent.markup if hasattr(sent.markup, "inline_keyboard") else None,
                )
        return fresh

    def texts(self) -> list[str]:
        return [s.text for s in self.new()]

    def last_with_buttons(self, user: int) -> Sent | None:
        for sent in reversed(self._all()):
            if sent.chat_id == user and hasattr(sent.markup, "inline_keyboard"):
                return sent
        return None

    def api_calls(self, kind: type) -> list[Any]:
        return [m for m in self.session.requests if isinstance(m, kind)]

    async def register(
        self,
        user: int = 1,
        *,
        weight: int = 80,
        height: int = 180,
        gender: str = "mies",
        nick: str | None = None,
    ) -> None:
        """Create an account directly in the database."""
        await self.store.users.create_or_update(user, nick or f"User{user}", weight, gender, height)
        self.new()


async def _revoke_terms(self, user: int = 1) -> None:
    """The user has an account, but has not accepted the terms."""
    found = await self.store.users.find(user)
    await self.store.users.update_fields(found, read_terms=False)


async def _drink_count(self) -> int:
    """How many drinks there are in the database, whoever they belong to."""
    total = 0
    async for account in self.store.users.scan():
        total += len(account.drinks)
    return total


Harness.revoke_terms = _revoke_terms
Harness.drink_count = _drink_count


def make_settings(tmp_path, **overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "bot_token": "42:TEST",
        "secret_key": "test-secret-key-that-is-long-enough-0123456789",
        "database_path": tmp_path / "data.sqlite3",
        "key_database_path": tmp_path / "keys.sqlite3",
        "admin_id": 999,
        "timezone": "Europe/Helsinki",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


async def make_harness(
    store, tmp_path, *, throttle: ThrottleMiddleware | None = None, **settings
) -> Harness:
    cfg = make_settings(tmp_path, **settings)
    session = FakeSession()
    bot = Bot("42:TEST", session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    # tests send many updates quickly: only the throttling tests use a real limit
    dp = build_dispatcher(
        store, cfg, throttle=throttle or ThrottleMiddleware(rate=1000, burst=100000)
    )
    return Harness(store, cfg, dp, bot, session)
