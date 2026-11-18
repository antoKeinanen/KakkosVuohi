"""Running on Cloudflare Workers: the D1 backend, stored conversations, the request handling."""

from __future__ import annotations

import json
from email.parser import BytesParser
from email.policy import HTTP
from urllib.parse import parse_qs

import pytest
from aiogram.fsm.storage.base import StorageKey
from aiogram.methods import SendMessage, SetWebhook
from conftest import SECRET
from fake_d1 import SqliteD1
from harness import FakeSession

from blakkisvuohi.conversations import DatabaseStorage
from blakkisvuohi.db import D1Database, TransactionConflict
from blakkisvuohi.db.database import DATA_MIGRATIONS
from blakkisvuohi.scheduler import purge_on_schedule
from blakkisvuohi.strings import S
from blakkisvuohi.workers import runtime
from blakkisvuohi.workers.session import encode_form

WEBHOOK_SECRET = "webhook-secret-0123456789"


async def open_d1(tmp_path, name="data.sqlite3"):
    client = SqliteD1(str(tmp_path / name))
    return await D1Database.open(client, DATA_MIGRATIONS), client


# -- the D1 backend -------------------------------------------------------------------------------


async def test_a_transaction_that_read_stale_data_writes_nothing(tmp_path):
    db, _ = await open_d1(tmp_path)
    other, _ = await open_d1(tmp_path)  # another isolate on the same database
    await db.execute("INSERT INTO meta (key, value) VALUES ('n', '1')")

    with pytest.raises(TransactionConflict):
        async with db.transaction() as tx:
            row = await tx.fetchone("SELECT value FROM meta WHERE key = 'n'")
            await other.execute("UPDATE meta SET value = '5' WHERE key = 'n'")
            await tx.execute("UPDATE meta SET value = ? WHERE key = 'n'", (int(row["value"]) + 1,))
            await tx.execute("INSERT INTO meta (key, value) VALUES ('m', 'x')")

    rows = await db.fetchall("SELECT key, value FROM meta ORDER BY key")
    assert [(r["key"], r["value"]) for r in rows] == [("n", "5")]  # the other write, not a mix


async def test_transactions_commit_atomically(tmp_path):
    db, _ = await open_d1(tmp_path)
    async with db.transaction() as tx:
        assert await tx.fetchone("SELECT 1 FROM meta") is None
        await tx.execute("INSERT INTO meta (key, value) VALUES ('a', '1')")
        assert await db.fetchone("SELECT 1 FROM meta") is None  # not before the commit
        await tx.execute("INSERT INTO meta (key, value) VALUES ('b', '2')")
    assert len(await db.fetchall("SELECT * FROM meta")) == 2

    with pytest.raises(Exception, match="UNIQUE"):
        async with db.transaction() as tx:
            await tx.execute("INSERT INTO meta (key, value) VALUES ('c', '3')")
            await tx.execute("INSERT INTO meta (key, value) VALUES ('a', 'again')")
    assert await db.fetchone("SELECT 1 FROM meta WHERE key = 'c'") is None

    with pytest.raises(ZeroDivisionError):
        async with db.transaction() as tx:
            await tx.execute("INSERT INTO meta (key, value) VALUES ('d', '4')")
            1 / 0  # noqa: B018
    assert await db.fetchone("SELECT 1 FROM meta WHERE key = 'd'") is None


async def test_a_read_only_transaction_sees_one_snapshot(tmp_path):
    db, _ = await open_d1(tmp_path)
    other, _ = await open_d1(tmp_path)
    async with db.transaction() as tx:  # nothing in between: fine
        await tx.fetchall("SELECT * FROM meta")
    with pytest.raises(TransactionConflict):
        async with db.transaction() as tx:
            await tx.fetchall("SELECT * FROM meta")
            await other.execute("INSERT INTO meta (key, value) VALUES ('x', 'y')")
            await tx.fetchall("SELECT * FROM users")


async def test_rows_work_by_name_and_by_index(tmp_path):
    db, _ = await open_d1(tmp_path)
    assert await db.execute("INSERT INTO meta (key, value) VALUES ('k', 'v')") == 1
    row = await db.fetchone("SELECT key, value FROM meta")
    assert (row[0], row["value"], list(row), row.keys(), len(row)) == (
        "k",
        "v",
        ["k", "v"],
        ["key", "value"],
        2,
    )


async def test_d1_migrations_run_once_and_refuse_a_newer_schema(tmp_path):
    db, client = await open_d1(tmp_path)
    await db.execute("INSERT INTO meta (key, value) VALUES ('kept', '1')")
    db, _ = await open_d1(tmp_path)  # again: nothing to do, nothing lost
    assert await db.fetchone("SELECT 1 FROM meta WHERE key = 'kept'") is not None
    client.conn.execute("UPDATE _d1_state SET schema_version = 99")
    with pytest.raises(RuntimeError, match="newer"):
        await open_d1(tmp_path)


# -- stored conversations -------------------------------------------------------------------------


def _key(user: int = 62461364, chat: int = 62461364) -> StorageKey:
    return StorageKey(bot_id=42, chat_id=chat, user_id=user)


async def test_conversations_are_stored_sealed_and_pseudonymous(tmp_path, crypto, clock):
    db, client = await open_d1(tmp_path)
    storage = DatabaseStorage(db, crypto, clock)
    await storage.set_state(_key(), "Tunnus:height")
    await storage.update_data(_key(), {"weight": 87, "nick": "Anto Keinänen"})

    assert await storage.get_state(_key()) == "Tunnus:height"
    assert await storage.get_data(_key()) == {"weight": 87, "nick": "Anto Keinänen"}
    assert await storage.get_state(_key(user=1, chat=1)) is None  # somebody else's
    assert await storage.get_data(_key(chat=-100)) == {}  # the same user in another chat

    raw = (tmp_path / "data.sqlite3").read_bytes()
    for needle in ("Anto", "Tunnus", "weight", "62461364"):
        assert needle.encode() not in raw, needle

    await storage.set_state(_key(), None)
    await storage.set_data(_key(), {})
    assert client.conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0] == 0


async def test_the_purge_ends_conversations_that_stopped(store, crypto, clock):
    storage = DatabaseStorage(store.db, crypto, clock)
    await storage.set_state(_key(user=1), "old")
    clock.advance(hours=24)
    await storage.set_state(_key(user=2), "yesterday")
    clock.advance(hours=24)
    await storage.set_state(_key(user=3), "today")
    await store.purge()
    assert [await storage.get_state(_key(user=u)) for u in (1, 2, 3)] == [
        None,
        "yesterday",
        "today",
    ]


# -- the purge on a Cron Trigger ------------------------------------------------------------------


async def test_the_hourly_cron_purges_at_the_purge_hour_or_to_catch_up(store, clock):
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("Europe/Helsinki")  # the clock starts at 12:40 there
    assert await purge_on_schedule(store, 13, tz, clock) is not None  # never purged: catch up
    clock.advance(minutes=30)  # 13:10
    assert await purge_on_schedule(store, 13, tz, clock) is not None  # the purge hour
    clock.advance(hours=1)  # 14:10
    assert await purge_on_schedule(store, 13, tz, clock) is None  # done for today
    clock.advance(hours=23)  # 13:10 the next day
    assert await purge_on_schedule(store, 13, tz, clock) is not None


# -- the request body to the Bot API --------------------------------------------------------------


def test_form_without_files_is_urlencoded():
    body, content_type = encode_form({"chat_id": "5", "text": "a&b=ä"}, {})
    assert content_type == "application/x-www-form-urlencoded"
    assert parse_qs(body.decode()) == {"chat_id": ["5"], "text": ["a&b=ä"]}


def test_form_with_files_is_multipart():
    png = bytes(range(256)) + b"\r\n--x"
    body, content_type = encode_form(
        {"chat_id": "5", "photo": "attach://abc", "caption": "Kuvaaja ä"},
        {"abc": ('kuva"aja.png', png)},
    )
    message = BytesParser(policy=HTTP).parsebytes(
        f"Content-Type: {content_type}\r\n\r\n".encode() + body
    )
    parts = {p.get_param("name", header="content-disposition"): p for p in message.iter_parts()}
    assert parts["chat_id"].get_content() == "5"
    assert parts["caption"].get_payload(decode=True).decode() == "Kuvaaja ä"
    assert parts["abc"].get_filename() == 'kuva"aja.png'
    assert parts["abc"].get_payload(decode=True) == png


# -- the Worker -----------------------------------------------------------------------------------


def worker_env(**overrides) -> dict:
    env = {
        "BOT_TOKEN": "42:TEST",
        "SECRET_KEY": SECRET,
        "WEBHOOK_SECRET": WEBHOOK_SECRET,
        "TIMEZONE": "Europe/Helsinki",
        "ADMIN_ID": "",
        "PURGE_HOUR": 12,
    }
    env.update(overrides)
    return env


async def build_runtime(tmp_path) -> tuple[runtime.Runtime, FakeSession]:
    session = FakeSession()
    rt = await runtime.build(
        runtime.settings_from(worker_env()),
        SqliteD1(str(tmp_path / "data.sqlite3")),
        SqliteD1(str(tmp_path / "keys.sqlite3")),
        session,
    )
    return rt, session


def message_update(update_id: int, text: str, user: int = 5) -> str:
    return json.dumps(
        {
            "update_id": update_id,
            "message": {
                "message_id": update_id,
                "date": 1_762_857_600,
                "chat": {"id": user, "type": "private"},
                "from": {"id": user, "is_bot": False, "first_name": "A", "username": "anto"},
                "text": text,
            },
        }
    )


def test_settings_come_from_the_worker_environment():
    settings = runtime.settings_from(worker_env(RETENTION_DAYS="3"))
    assert (settings.bot_mode, settings.retention_days, settings.admin_id) == ("worker", 3, None)
    with pytest.raises(ValueError, match="WEBHOOK_SECRET"):
        runtime.settings_from(worker_env(WEBHOOK_SECRET="short"))


async def test_only_telegram_can_post_updates(tmp_path):
    rt, session = await build_runtime(tmp_path)
    post = runtime.handle_request
    path, origin = rt.webhook_path, "https://bot.example.dev"
    assert path.startswith("/webhook/") and len(path) > 40
    good = {runtime.SECRET_HEADER: WEBHOOK_SECRET}

    assert await post(rt, "GET", "/healthz", {}, "", origin) == (200, '{"status":"ok"}')
    for headers in ({}, {runtime.SECRET_HEADER: "wrong"}):
        assert (await post(rt, "POST", path, headers, message_update(1, "/moro"), origin))[0] == 401
    assert (await post(rt, "POST", "/webhook/guess", good, message_update(1, "/moro"), origin))[
        0
    ] == 404
    assert (await post(rt, "GET", path, good, "", origin))[0] == 404
    assert (await post(rt, "POST", path, good, "not json", origin))[0] == 400
    assert (await post(rt, "POST", path, good, "[1]", origin))[0] == 400
    assert session.requests == []  # nothing got through

    assert await post(rt, "POST", path, good, message_update(1, "/tunnus"), origin) == (200, "{}")
    (sent,) = session.requests
    assert isinstance(sent, SendMessage) and sent.text == S.commands.tunnus.start


async def test_conversations_continue_in_a_new_isolate(tmp_path):
    """Every request may run in a fresh isolate: what was said before must not be forgotten."""
    good = {runtime.SECRET_HEADER: WEBHOOK_SECRET}
    replies = []
    for update_id, text in enumerate(["/tunnus", "80", "182", "Mies", "Kyllä"], start=1):
        rt, session = await build_runtime(tmp_path)  # a new isolate every time
        status, _ = await runtime.handle_request(
            rt, "POST", rt.webhook_path, good, message_update(update_id, text), "https://x.dev"
        )
        assert status == 200
        replies += [m.text for m in session.requests if isinstance(m, SendMessage)]
    assert replies[-1] == S.commands.tunnus.new_user.format(username="anto")
    user = await rt.store.users.find(5)
    assert (user.weight, user.height, user.gender) == (80, 180, "mies")


async def test_the_webhook_is_registered_on_request_of_the_operator(tmp_path):
    rt, session = await build_runtime(tmp_path)
    origin = "https://kakkosvuohi.example.workers.dev"
    for headers in ({}, {"authorization": "Bearer wrong"}, {"authorization": WEBHOOK_SECRET}):
        assert (await runtime.handle_request(rt, "POST", "/setup-webhook", headers, "", origin))[
            0
        ] == 401
    assert session.requests == []

    headers = {"authorization": f"Bearer {WEBHOOK_SECRET}"}
    status, _ = await runtime.handle_request(rt, "POST", "/setup-webhook", headers, "", origin)
    assert status == 200
    (call,) = session.requests
    assert isinstance(call, SetWebhook)
    assert call.url == origin + rt.webhook_path
    assert call.secret_token == WEBHOOK_SECRET
    assert call.max_connections == 1  # one update at a time
    assert call.allowed_updates == ["message", "callback_query"]
