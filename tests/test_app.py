"""Webhook security, error handling and the startup checks."""

import logging

from aiohttp.test_utils import TestClient, TestServer
from harness import make_harness

from blakkisvuohi.app import ALLOWED_UPDATES, build_dispatcher, create_webhook_app
from blakkisvuohi.strings import S


async def test_webhook_rejects_requests_without_the_secret_token(h):
    app = create_webhook_app(h.bot, h.dp, path="/webhook/abc", secret="s" * 20)
    update = {
        "update_id": 1,
        "message": {
            "message_id": 1,
            "date": 1,
            "chat": {"id": 1, "type": "private"},
            "from": {"id": 1, "is_bot": False, "first_name": "X"},
            "text": "/about",
        },
    }
    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/webhook/abc", json=update)
        assert resp.status == 401
        resp = await client.post(
            "/webhook/abc", json=update, headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"}
        )
        assert resp.status == 401
        assert h.new() == []  # nothing was processed

        resp = await client.post(
            "/webhook/abc", json=update, headers={"X-Telegram-Bot-Api-Secret-Token": "s" * 20}
        )
        assert resp.status == 200
        assert (await client.post("/webhook/other", json=update)).status == 404  # unguessable path
        health = await client.get("/healthz")
        assert await health.json() == {"status": "ok"}
        assert "version" not in await health.text()


def test_only_the_needed_update_types_are_requested():
    assert ALLOWED_UPDATES == ["message", "callback_query"]


async def test_errors_are_reported_to_the_user_and_admin_without_leaking_input(
    h, monkeypatch, caplog
):
    await h.register()

    async def boom(*args, **kwargs):
        raise RuntimeError("database exploded with <secret> details")

    monkeypatch.setattr(h.store.drinks, "add", boom)
    import blakkisvuohi.app as app

    app._last_admin_notice = 0.0
    with caplog.at_level(logging.ERROR):
        await h.say("/kalja033")
    texts = {(s.chat_id, s.text) for s in h.new()}
    assert (1, S.commands.blakkis.error) in texts  # the user gets a generic message
    (admin,) = [t for chat, t in texts if chat == 999]
    assert "RuntimeError" in admin and "&lt;secret&gt;" in admin  # escaped
    assert "/kalja033" in admin
    assert "Unhandled error" in caplog.text

    # a second error right after does not spam the admin
    await h.say("/kalja033")
    assert [s for s in h.new() if s.chat_id == 999] == []


async def test_user_input_is_not_forwarded_to_the_admin(h, monkeypatch):
    await h.register()

    async def boom(*args, **kwargs):
        raise RuntimeError("x")

    monkeypatch.setattr(h.store.users, "find", boom)
    import blakkisvuohi.app as app

    app._last_admin_notice = 0.0
    await h.say("/about")
    admin = [s.text for s in h.new() if s.chat_id == 999]
    assert admin and "/about" in admin[0]
    await h.say("my private text 12345")
    app._last_admin_notice = 0.0
    await h.say("my private text 12345")
    assert all("private text" not in s.text for s in h.new() if s.chat_id == 999)


async def test_blocking_the_bot_is_not_an_error(h):
    from aiogram.exceptions import TelegramForbiddenError
    from aiogram.methods import SendMessage

    await h.register()
    h.session.fail_with[1] = TelegramForbiddenError(
        method=SendMessage(chat_id=1, text="x"), message="Forbidden: bot was blocked by the user"
    )
    await h.say("/about")  # must not raise, must not notify the admin
    assert [s for s in h.new() if s.chat_id == 999] == []


async def test_dispatchers_can_be_built_repeatedly(store, tmp_path):
    for _ in range(3):
        await make_harness(store, tmp_path)
    assert build_dispatcher is not None


async def test_startup_runs_the_purge_and_shuts_down_cleanly(tmp_path, monkeypatch):
    """The real run(): opens both databases, starts the purge task, stops everything on exit."""
    import asyncio

    from aiogram import Bot, Dispatcher
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode
    from harness import FakeSession, make_settings

    import blakkisvuohi.app as app
    from blakkisvuohi.db import Store
    from blakkisvuohi.security import Crypto

    settings = make_settings(tmp_path)
    session = FakeSession()
    seen = {}

    def fake_bot(token, default=None):
        return Bot(token, session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

    async def fake_polling(self, bot, **kwargs):
        seen["allowed_updates"] = kwargs["allowed_updates"]
        await asyncio.sleep(0.2)  # long enough for the startup purge to run

    monkeypatch.setattr(app, "Bot", fake_bot)
    monkeypatch.setattr(Dispatcher, "start_polling", fake_polling)

    await app.run(settings)

    assert seen["allowed_updates"] == ["message", "callback_query"]
    assert [type(m).__name__ for m in session.requests] == ["DeleteWebhook"]
    # a purge happened at startup (nothing had ever been purged), and everything was closed
    store = await Store.open(
        settings.database_path,
        settings.key_database_path,
        Crypto(settings.secret_key.get_secret_value()),
    )
    try:
        assert await store.purger.last_run() is not None
    finally:
        await store.close()
    assert not [t for t in asyncio.all_tasks() if t.get_name() == "purge" and not t.done()]
