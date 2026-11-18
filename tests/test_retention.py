"""Retention: everything older than a week goes, every day around noon."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from blakkisvuohi.db import RetentionPolicy, Store, codec
from blakkisvuohi.scheduler import RETRY_AFTER, next_run, purge_forever, purge_if_due
from blakkisvuohi.strings import S

BEER = 12241
HELSINKI = ZoneInfo("Europe/Helsinki")


async def make_user(store: Store, telegram_id: int = 1, nick: str = "Tester"):
    user, _ = await store.users.create_or_update(telegram_id, nick, 80, "mies", 180)
    return user


async def stored_drinks(store: Store, user):
    """What is physically in the database, whatever the read side filters out."""
    row = await store.db.fetchone("SELECT drinks FROM users WHERE user_id = ?", (user.user_id,))
    key = await store.vault.get(user.user_id)
    return codec.open_drinks(key, user.user_id, row["drinks"])


# -- reads already ignore what is old ----------------------------------------------------------------


async def test_old_drinks_are_ignored_even_before_the_purge_has_run(store, clock):
    user = await make_user(store)
    await store.drinks.add(user, BEER, "old")
    clock.advance(hours=24 * 6)
    await store.drinks.add(user, BEER, "recent")
    clock.advance(hours=24 + 1)  # "old" is now 7 days and an hour old
    assert [d.description for d in await store.drinks.since(user, 24 * 30)] == ["recent"]
    assert (await store.drinks.sum_for_hours(user, 24 * 30)).sum == BEER
    assert (await store.drinks.last(user)).description == "recent"
    assert [d.description for d in await stored_drinks(store, user)] == ["old", "recent"]


async def test_old_drinks_do_not_count_in_groups_or_stats(store, clock):
    user = await make_user(store)
    await store.groups.join(user, -100)
    await store.drinks.add(user, BEER, "old")
    clock.advance(hours=24 * 8)
    assert (await store.stats.group_stats(-100, 24 * 30)).top10 == []
    assert (await store.stats.global_stats()).drinks_now == 0
    assert (await store.stats.global_stats()).drinks_total == 1  # the counter is not personal data


# -- the purge --------------------------------------------------------------------------------------


async def test_purge_deletes_drinks_older_than_a_week(store, clock):
    user = await make_user(store)
    await store.drinks.add(user, BEER, "old")
    clock.advance(hours=24 * 3)
    await store.drinks.add(user, BEER, "middle")
    clock.advance(hours=24 * 3)
    await store.users.touch(user)
    await store.drinks.add(user, BEER, "new")
    clock.advance(hours=24 + 1)
    await store.users.touch(user)

    report = await store.purge()

    assert report.drinks_deleted == 1 and report.accounts_deleted == 0
    assert [d.description for d in await stored_drinks(store, user)] == ["middle", "new"]


async def test_purge_deletes_accounts_that_have_not_been_used_for_a_week(store, clock):
    gone = await make_user(store, 1, "Gone")
    kept = await make_user(store, 2, "Kept")
    await store.groups.join(gone, -100)
    await store.groups.join(kept, -100)
    await store.drinks.add(gone, BEER, "x")
    clock.advance(hours=24 * 5)
    await store.users.touch(kept)  # Kept uses the bot, Gone does not
    clock.advance(hours=24 * 3)

    report = await store.purge()

    assert report.accounts_scanned == 2 and report.accounts_deleted == 1
    assert report.drinks_deleted == 1
    assert await store.users.find(1) is None
    assert await store.vault.get(gone.user_id) is None
    assert await store.db.fetchone("SELECT 1 FROM users WHERE user_id = ?", (gone.user_id,)) is None
    assert (await store.db.fetchone("SELECT COUNT(*) FROM users_in_groups"))[0] == 1
    assert (await store.users.find(2)).nick == "Kept"


async def test_the_account_expiry_boundary_is_a_week_of_days(store, clock):
    user = await make_user(store)
    clock.advance(hours=24 * 7)
    assert (await store.purge()).accounts_deleted == 0  # last used 7 days ago: still there
    clock.advance(hours=24 * 1)
    assert (await store.purge()).accounts_deleted == 1  # 8 days: gone
    assert await store.users.find(1) is None
    assert user  # silence unused


async def test_retention_is_configurable(tmp_path, crypto, clock):
    store = await Store.open(
        tmp_path / "d.sqlite3", tmp_path / "k.sqlite3", crypto, clock, RetentionPolicy(2, 30)
    )
    try:
        user = await make_user(store)
        await store.drinks.add(user, BEER, "x")
        clock.advance(hours=24 * 3)
        await store.purge()
        assert await store.drinks.since(user, 24 * 30) == []  # the drink is older than 2 days
        assert await store.users.find(1) is not None  # but accounts live for 30 days
    finally:
        await store.close()


async def test_purge_removes_leftovers_that_nobody_can_use(store):
    user = await make_user(store, 1)
    await make_user(store, 2)
    # data whose key is gone (e.g. the key database was restored from an older copy)
    await store.vault.destroy(user.user_id)
    # a key whose data is gone
    stray = store.crypto.user_id(777)
    await store.vault.create(stray)

    report = await store.purge()

    assert report.orphans_removed == 2
    assert report.accounts_scanned == 1
    assert await store.db.fetchone("SELECT 1 FROM users WHERE user_id = ?", (user.user_id,)) is None
    assert await store.vault.get(stray) is None
    assert await store.users.find(2) is not None


async def test_purged_data_leaves_no_trace_in_the_files(store, backend, clock, tmp_path):
    if backend == "d1":
        pytest.skip("D1 manages its storage: no secure_delete, VACUUM or checkpoint (see README)")
    user = await make_user(store, 1, "Doomed")
    row = await store.db.fetchone("SELECT profile, drinks FROM users")
    wrapped = (await store.keydb.fetchone("SELECT wrapped_key FROM user_keys"))["wrapped_key"]
    clock.advance(hours=24 * 8)

    await store.purge()

    for name, needles in (
        ("data.sqlite3", (row["profile"], row["drinks"])),
        ("keys.sqlite3", (wrapped,)),
    ):
        raw = b"".join(p.read_bytes() for p in tmp_path.glob(f"{name}*") if p.is_file())
        for needle in needles:
            assert needle.encode() not in raw, f"deleted ciphertext is still in {name}"
    assert user


async def test_purge_records_when_it_ran_and_refuses_a_clock_that_went_backwards(store, clock):
    await make_user(store)
    assert await store.purger.last_run() is None
    await store.purge()
    assert await store.purger.last_run() == clock.now
    clock.now -= 3600
    with pytest.raises(RuntimeError, match="clock"):
        await store.purge()
    assert await store.users.find(1) is not None  # nothing was deleted


async def test_purge_while_the_bot_is_in_use(store, clock):
    users = [await make_user(store, i, f"U{i}") for i in range(1, 6)]
    for u in users:
        await store.drinks.add(u, BEER, "old")
    clock.advance(hours=24 * 7 + 1)
    for u in users:
        await store.users.touch(u)
    await asyncio.gather(
        store.purge(),
        *(store.drinks.add(u, BEER, "during the purge") for u in users),
    )
    for u in users:
        assert [d.description for d in await store.drinks.since(u, 24 * 7)] == ["during the purge"]


async def test_corrupted_accounts_do_not_stop_the_purge(store, clock):
    bad = await make_user(store, 1)
    await make_user(store, 2)
    await store.db.execute(
        "UPDATE users SET drinks = 'v1.garbage' WHERE user_id = ?", (bad.user_id,)
    )
    clock.advance(hours=24)
    report = await store.purge()
    assert report.accounts_scanned == 1  # the readable one


# -- using the bot keeps the account ----------------------------------------------------------------


async def test_using_the_bot_keeps_the_account_alive(h, clock):
    await h.register(1)
    await h.register(2)
    clock.advance(hours=24 * 5)
    await h.say("/about", user=1)
    h.new()
    clock.advance(hours=24 * 5)  # 10 days since registering, 5 since user 1 last used the bot
    report = await h.store.purge()
    assert report.accounts_deleted == 1
    assert await h.store.users.find(1) is not None
    assert await h.store.users.find(2) is None
    await h.say("/kalja033", user=2)
    assert h.texts() == [S.commands.blakkis.user404]  # they have to sign up again


async def test_purge_command_for_the_admin(h, clock):
    await h.register(1)
    clock.advance(hours=24 * 9)
    await h.say("/admin_purge", user=5)
    assert h.texts() == [S.commands.blakkis.unauthorized]
    await h.say("/admin_purge", user=999)
    (text,) = h.texts()
    assert "poistettu 1 tunnusta" in text
    assert await h.store.users.find(1) is None


# -- scheduling -------------------------------------------------------------------------------------


def local(*args):
    return datetime(*args, tzinfo=HELSINKI).timestamp()


def test_next_run_is_the_coming_noon():
    assert next_run(local(2025, 11, 11, 9, 30), 12, HELSINKI) == local(2025, 11, 11, 12)
    assert next_run(local(2025, 11, 11, 12, 0, 1), 12, HELSINKI) == local(2025, 11, 12, 12)
    assert next_run(local(2025, 11, 11, 23, 59), 12, HELSINKI) == local(2025, 11, 12, 12)
    assert next_run(local(2025, 11, 11, 12, 0), 12, HELSINKI) == local(
        2025, 11, 12, 12
    )  # not "now"


def test_next_run_follows_local_time_through_daylight_saving():
    # clocks go forward on 2026-03-29: the day is 23 hours long, noon is still noon
    before = local(2026, 3, 28, 13)
    nxt = next_run(before, 12, HELSINKI)
    assert nxt == local(2026, 3, 29, 12)
    assert datetime.fromtimestamp(nxt, UTC).hour == 9  # UTC+3 in summer time
    assert (nxt - before) / 3600 == 22


def test_next_run_hour_is_configurable():
    assert next_run(local(2025, 11, 11, 1), 3, HELSINKI) == local(2025, 11, 11, 3)


async def test_purge_if_due(store, clock):
    await make_user(store)
    assert await purge_if_due(store, clock) is not None  # never purged
    assert await purge_if_due(store, clock) is None  # just did
    clock.advance(hours=23)
    assert await purge_if_due(store, clock) is None
    clock.advance(hours=2)
    assert await purge_if_due(store, clock) is not None  # the bot was down at noon


class StopLoop(BaseException):
    pass


async def run_loop(store, clock, sleeps_allowed, advance_to_next_run=True):
    delays: list[float] = []

    async def fake_sleep(delay):
        delays.append(delay)
        if len(delays) > sleeps_allowed:
            raise StopLoop
        if advance_to_next_run:
            clock.now += delay

    with pytest.raises(StopLoop):
        await purge_forever(store, 12, HELSINKI, clock, fake_sleep)
    return delays


async def test_the_loop_purges_every_day_at_noon(store, clock):
    clock.now = local(2025, 11, 11, 9)
    user = await make_user(store)
    await store.drinks.add(user, BEER, "x")
    purges = []
    original = store.purge

    async def counting_purge():
        purges.append(clock.now)
        return await original()

    store.purge = counting_purge
    delays = await run_loop(store, clock, sleeps_allowed=3)

    # startup catch-up at 09:00, then noon, noon, noon
    assert purges[0] == local(2025, 11, 11, 9)
    assert purges[1:] == [local(2025, 11, 11, 12), local(2025, 11, 12, 12), local(2025, 11, 13, 12)]
    assert delays[:3] == [3 * 3600, 24 * 3600, 24 * 3600]


async def test_a_failing_purge_is_retried_and_never_kills_the_loop(store, clock):
    clock.now = local(2025, 11, 11, 9)
    calls = []

    async def failing_purge():
        calls.append(clock.now)
        raise RuntimeError("disk full")

    store.purge = failing_purge
    delays = await run_loop(store, clock, sleeps_allowed=2)
    assert delays[0] == RETRY_AFTER  # the startup purge failed: retry in an hour
    assert len(calls) == 3
