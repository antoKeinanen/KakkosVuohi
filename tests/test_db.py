from __future__ import annotations

import asyncio
import stat

import pytest

from blakkisvuohi.announcements import ANNOUNCEMENTS
from blakkisvuohi.db import AccountGone, LateDrink, Store, WrongSecretKey
from blakkisvuohi.db.drinks import MAX_DRINKS_PER_USER, TooManyDrinks
from blakkisvuohi.db.models import day_number
from blakkisvuohi.security import Crypto, DecryptionError

BEER = 12241  # 0.33l 4.7%


async def make_user(store: Store, telegram_id: int = 1, nick: str = "Tester", **kw):
    user, _ = await store.users.create_or_update(
        telegram_id, nick, kw.get("weight", 80), kw.get("gender", "mies"), kw.get("height", 180)
    )
    return user


async def open_store(tmp_path, crypto, key="keys.sqlite3", data="data.sqlite3"):
    return await Store.open(tmp_path / data, tmp_path / key, crypto)


# -- storage hygiene ------------------------------------------------------------------------------


async def test_database_files_are_private(tmp_path, crypto):
    store = await Store.open(
        tmp_path / "d" / "data.sqlite3", tmp_path / "k" / "keys.sqlite3", crypto
    )
    await store.close()
    for directory, name in (("d", "data.sqlite3"), ("k", "keys.sqlite3")):
        path = tmp_path / directory / name
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700


async def test_data_and_keys_must_be_different_files(tmp_path, crypto):
    with pytest.raises(ValueError, match="different"):
        await Store.open(tmp_path / "x.sqlite3", tmp_path / "x.sqlite3", crypto)


async def test_nothing_personal_is_stored_in_clear(store, crypto, tmp_path):
    user = await make_user(store, 62461364, "Anto Keinänen", weight=85, height=185)
    await store.drinks.add(user, BEER, "🍺 33cl 4.7% secret-brand")
    await store.groups.join(user, -1001234567)
    await store.db.checkpoint()
    await store.keydb.checkpoint()

    for name in ("data.sqlite3", "keys.sqlite3"):
        raw = (tmp_path / name).read_bytes()
        for needle in ("Anto", "Keinänen", "secret-brand", "62461364", "1001234567", "mies"):
            assert needle.encode() not in raw, f"{needle!r} is readable in {name}"
    # what is there: pseudonyms
    rows = await store.db.fetchall("SELECT user_id FROM users")
    assert [r["user_id"] for r in rows] == [crypto.user_id(62461364)]


async def test_the_data_alone_is_useless_without_the_keys(store, crypto, tmp_path):
    """A stolen copy of the data database (a backup, a SQL injection dump...) shows nothing."""
    await make_user(store, 1, "Alice")
    stolen = await Store.open(
        tmp_path / "data.sqlite3.copy", tmp_path / "other-keys.sqlite3", crypto
    )
    row = await store.db.fetchone("SELECT user_id, profile, drinks FROM users")
    await stolen.db.execute(
        "INSERT INTO users (user_id, profile, drinks) VALUES (?, ?, ?)",
        (row["user_id"], row["profile"], row["drinks"]),
    )
    assert await stolen.users.find(1) is None  # no key: not readable even with the master secret
    await stolen.close()


async def test_wrong_secret_key_is_refused(tmp_path, crypto):
    (await open_store(tmp_path, crypto))  # creates the databases
    other = Crypto("another-secret-key-that-is-long-enough-xyz")
    with pytest.raises(WrongSecretKey):
        await open_store(tmp_path, other)
    # also when only the key database is from another installation
    await asyncio.sleep(0)
    with pytest.raises(WrongSecretKey):
        await Store.open(tmp_path / "fresh.sqlite3", tmp_path / "keys.sqlite3", other)
    store = await open_store(tmp_path, crypto)  # the right key still works
    await store.close()


async def test_migrations_are_idempotent(tmp_path, crypto):
    for _ in range(3):
        store = await open_store(tmp_path, crypto)
        await store.close()


# -- users ----------------------------------------------------------------------------------------


async def test_create_find_update(store, clock):
    assert await store.users.find(1) is None
    user, created = await store.users.create_or_update(1, "Anto", 80, "mies", 180)
    assert created and user.nick == "Anto" and user.read_terms
    assert user.read_announcements == len(ANNOUNCEMENTS)  # new users skip old announcements
    assert user.last_active_day == day_number(clock.now)

    again, created = await store.users.create_or_update(1, "Anto K", 75, "nainen", 170)
    assert not created
    assert (again.nick, again.weight, again.gender, again.height) == ("Anto K", 75, "nainen", 170)

    await store.users.update_weight(again, 90)
    await store.users.update_height(again, 190)
    await store.users.update_gender(again, "mies")
    await store.users.update_nick(again, "Uusi")
    await store.users.update_read_announcements(again, 3)
    found = await store.users.find(1)
    assert (found.weight, found.height, found.gender, found.nick, found.read_announcements) == (
        90,
        190,
        "mies",
        "Uusi",
        3,
    )


async def test_weight_and_height_are_stored_coarsely(store):
    user = await make_user(store, weight=82, height=183)
    assert (user.weight, user.height) == (80, 185)
    await store.users.update_weight(user, 83)
    await store.users.update_height(user, 238)
    found = await store.users.find(1)
    assert (found.weight, found.height) == (85, 240)
    await store.users.update_weight(user, 20)
    await store.users.update_weight(user, 250)
    assert (await store.users.find(1)).weight == 250


async def test_invalid_profiles_are_never_written(store):
    user = await make_user(store)
    for field, value in (
        ("weight", 5),
        ("height", 500),
        ("gender", "x"),
        ("nick", ""),
        ("read_announcements", -1),
    ):
        with pytest.raises(ValueError, match="out of range|invalid"):
            await store.users.update_fields(user, **{field: value})
    assert (await store.users.find(1)).weight == 80


async def test_a_profile_cannot_be_moved_to_another_user(store):
    await make_user(store, 1, "Alice")
    await make_user(store, 2, "Bob")
    alice = await store.db.fetchone(
        "SELECT profile FROM users WHERE user_id = ?", (store.crypto.user_id(1),)
    )
    await store.db.execute(
        "UPDATE users SET profile = ? WHERE user_id = ?",
        (alice["profile"], store.crypto.user_id(2)),
    )
    with pytest.raises(DecryptionError):
        await store.users.find(2)


async def test_concurrent_profile_changes_are_not_lost(store):
    user = await make_user(store)
    await asyncio.gather(
        store.users.update_weight(user, 95),
        store.users.update_height(user, 200),
        store.users.update_nick(user, "Changed"),
        store.users.update_read_announcements(user, 2),
    )
    found = await store.users.find(1)
    assert (found.weight, found.height, found.nick, found.read_announcements) == (
        95,
        200,
        "Changed",
        2,
    )


async def test_touch_records_use_at_most_once_a_day(store, clock):
    user = await make_user(store)
    day = user.last_active_day
    await store.users.touch(user)  # same day: nothing to write
    clock.advance(hours=30)
    await store.users.touch(user)
    assert (await store.users.find(1)).last_active_day == day + 1
    await store.users.touch(await store.users.find(1))


# -- deleting and crypto-shredding ------------------------------------------------------------------


async def test_delete_removes_everything_about_the_user(store):
    user = await make_user(store, 1)
    other = await make_user(store, 2, "Other")
    await store.drinks.add(user, BEER, "beer")
    await store.drinks.add(other, BEER, "beer")
    await store.groups.join(user, -100)
    await store.groups.join(other, -100)

    await store.users.delete(user)

    assert await store.users.find(1) is None
    assert (await store.users.export(1)).is_empty()
    assert await store.vault.get(user.user_id) is None
    assert await store.users.find(2) is not None  # others are untouched
    assert len(await store.drinks.since(other, 24)) == 1
    assert (await store.db.fetchone("SELECT COUNT(*) FROM users_in_groups"))[0] == 1


async def test_deleted_data_stays_unreadable_even_if_a_copy_of_it_survives(store):
    """Crypto-shredding: a backup of the data database is worthless once the key is destroyed."""
    user = await make_user(store, 1, "Alice")
    await store.drinks.add(user, BEER, "beer")
    row = await store.db.fetchone("SELECT user_id, profile, drinks FROM users")  # the 'backup'

    await store.users.delete(user)
    await store.db.execute(
        "INSERT INTO users (user_id, profile, drinks) VALUES (?, ?, ?)",
        (row["user_id"], row["profile"], row["drinks"]),
    )  # the old data comes back

    assert await store.users.find(1) is None
    assert (await store.users.export(1)).is_empty()
    # and the same person signing up again does not get the old data back
    fresh, created = await store.users.create_or_update(1, "Alice again", 70, "nainen", 170)
    assert created
    assert await store.drinks.since(fresh, 24 * 7) == []


async def test_operations_on_a_deleted_account_fail_cleanly(store):
    user = await make_user(store)
    await store.users.delete(user)
    with pytest.raises(AccountGone):
        await store.drinks.add(user, BEER, "x")
    with pytest.raises(AccountGone):
        await store.users.update_weight(user, 70)
    await store.users.touch(user)  # being touched by a late request is harmless


async def test_export(store, clock):
    user = await make_user(store, 1, "=HYPERLINK()")
    await store.drinks.add(user, BEER, "beer")
    await store.groups.join(user, -100)
    data = await store.users.export(1)
    assert data.user.columns[:3] == ["user_id", "nick", "weight"]
    assert data.user.rows[0][1] == "=HYPERLINK()"  # decrypted
    assert data.drinks.columns == ["created", "alcohol", "description"]
    assert data.drinks.rows[0][0].startswith("2025-11-11T10:40:00")
    assert len(data.groups.rows) == 1
    assert (await store.users.export(999)).is_empty()


# -- drinks ---------------------------------------------------------------------------------------


async def test_drink_history_and_undo(store, clock):
    user = await make_user(store)
    await store.drinks.add(user, BEER, "first")
    clock.advance(minutes=30)
    await store.drinks.add(user, 2 * BEER, "second")
    clock.advance(minutes=30)

    assert [d.description for d in await store.drinks.since(user, 24)] == ["first", "second"]
    assert [d.description for d in await store.drinks.last_hours(user, 24)] == ["second", "first"]
    assert [d.description for d in await store.drinks.last_hours(user, 0.75)] == ["second"]
    assert (await store.drinks.last(user)).description == "second"

    await store.drinks.undo_last(user)
    assert [d.description for d in await store.drinks.since(user, 24)] == ["first"]
    await store.drinks.undo_last(user)
    await store.drinks.undo_last(user)  # nothing left: no error
    assert await store.drinks.last(user) is None


async def test_undo_removes_only_one_drink_even_in_the_same_second(store):
    user = await make_user(store)
    await store.drinks.add(user, BEER, "a")
    await store.drinks.add(user, BEER, "b")
    await store.drinks.undo_last(user)
    assert [d.description for d in await store.drinks.since(user, 24)] == ["a"]


async def test_late_drinks_are_spread_over_the_period(store, clock):
    user = await make_user(store)
    await store.drinks.add_late(user, [LateDrink(f"d{i}", BEER) for i in range(3)], 2)
    stored = await store.drinks.since(user, 3)
    assert [d.description for d in stored] == ["d0", "d1", "d2"]
    assert [clock.now - d.created for d in stored] == [7200, 3600, 0]

    other = await make_user(store, 2)
    await store.drinks.add_late(other, [LateDrink("only", BEER)], 1.5)
    (only,) = await store.drinks.since(other, 3)
    assert clock.now - only.created == 5400


async def test_drinks_stay_in_time_order_when_added_late(store, clock):
    user = await make_user(store)
    await store.drinks.add(user, BEER, "now")
    await store.drinks.add_late(user, [LateDrink("earlier", BEER)], 2)
    assert [d.description for d in await store.drinks.since(user, 5)] == ["earlier", "now"]
    assert (await store.drinks.last(user)).description == "now"


async def test_ebac_after_a_drink(store, clock):
    user = await make_user(store)
    assert (await store.drinks.ebac(user)).permilles == 0
    await store.drinks.add(user, BEER, "beer")
    clock.advance(minutes=45)
    ebac = await store.drinks.ebac(user)
    assert ebac.permilles > 0 and ebac.grams > 0
    clock.advance(hours=10)
    assert (await store.drinks.ebac(user)).permilles == 0


async def test_sum_for_hours(store, clock):
    user = await make_user(store)
    assert (await store.drinks.sum_for_hours(user, 24)).sum == 0
    await store.drinks.add(user, 1000, "a")
    clock.advance(hours=30)
    await store.drinks.add(user, 2000, "b")
    clock.advance(hours=1)
    assert (await store.drinks.sum_for_hours(user, 24)).sum == 2000
    total = await store.drinks.sum_for_hours(user, 48)
    assert total.sum == 3000
    assert total.first_drink == int(clock.now - 31 * 3600)


async def test_last_unique_for_quick_pick_buttons(store, clock):
    user = await make_user(store)
    for name in ["beer", "wine", "beer", "Jälkikellotus 33cl 4.7%", "shot", "wine"]:
        await store.drinks.add(user, BEER, name)
        clock.advance(minutes=1)
    unique = await store.drinks.last_unique(user, 2, "Jälkikellotus")
    assert [d.description for d in unique] == ["wine", "shot"]
    everything = await store.drinks.last_unique(user, 10)
    assert [d.description for d in everything] == [
        "wine",
        "shot",
        "Jälkikellotus 33cl 4.7%",
        "beer",
    ]


async def test_drink_count_is_capped(store, monkeypatch):
    from blakkisvuohi.db import drinks

    monkeypatch.setattr(drinks, "MAX_DRINKS_PER_USER", 3)
    user = await make_user(store)
    await store.drinks.add_late(user, [LateDrink("x", BEER)] * 3, 1)
    with pytest.raises(TooManyDrinks):
        await store.drinks.add(user, BEER, "one too many")
    assert len(await store.drinks.since(user, 24)) == 3
    assert MAX_DRINKS_PER_USER >= 100


async def test_ciphertext_size_does_not_tell_how_many_drinks(store):
    user = await make_user(store)
    await store.drinks.add(user, BEER, "🍺 33cl 4.7%")
    size = lambda: store.db.fetchone("SELECT length(drinks) AS n FROM users")  # noqa: E731
    one = (await size())["n"]
    for _ in range(9):
        await store.drinks.add(user, BEER, "🍺 33cl 4.7%")
    assert (await size())["n"] == one


async def test_global_counters_follow_drinks_and_undo(store):
    user = await make_user(store)
    await store.drinks.add(user, 1000, "a")
    await store.drinks.add_late(user, [LateDrink("b", 2000), LateDrink("c", 3000)], 1)
    assert await store.stats._counter("drinks_total") == 3
    assert await store.stats._counter("alcohol_total") == 6000
    await store.drinks.undo_last(user)
    assert await store.stats._counter("drinks_total") == 2


async def test_concurrent_writes_do_not_lose_drinks(store):
    users = [await make_user(store, i, f"U{i}") for i in range(1, 6)]
    await asyncio.gather(
        *(store.drinks.add_late(u, [LateDrink("x", BEER)] * 5, 2) for u in users),
        *(store.drinks.add(u, BEER, "y") for u in users),
        *(store.drinks.add(u, BEER, "z") for u in users),
    )
    for u in users:
        assert len(await store.drinks.since(u, 24)) == 7
    assert await store.stats._counter("drinks_total") == 35


# -- groups and stats -----------------------------------------------------------------------------


async def test_group_listings(store, clock):
    heavy = await make_user(store, 1, "Heavy")
    light = await make_user(store, 2, "Light")
    outsider = await make_user(store, 3, "Outsider")
    sober = await make_user(store, 4, "Sober")
    for u in (heavy, light, sober):
        await store.groups.join(u, -100)
    await store.groups.join(outsider, -200)
    for _ in range(4):
        await store.drinks.add(heavy, BEER, "beer")
    await store.drinks.add(light, BEER, "beer")
    await store.drinks.add(outsider, BEER, "beer")
    clock.advance(minutes=40)

    listing = await store.groups.permilles_listing(-100)
    assert [e.nick for e in listing] == ["Heavy", "Light"]
    assert listing[0].value > listing[1].value > 0
    assert listing[0].standard_drinks_12h == pytest.approx(4 * BEER / 12000)
    assert listing[1].standard_drinks_24h == pytest.approx(BEER / 12000)

    doses = await store.groups.standard_drinks_listing(-100)
    assert [e.nick for e in doses] == ["Heavy", "Light"]

    await store.groups.leave(heavy, -100)
    assert [e.nick for e in await store.groups.permilles_listing(-100)] == ["Light"]
    await store.groups.join(light, -100)  # joining twice is fine
    assert [e.nick for e in await store.groups.permilles_listing(-100)] == ["Light"]
    assert await store.groups.permilles_listing(-999) == []


async def test_group_stats(store):
    a = await make_user(store, 1, "A")
    b = await make_user(store, 2, "B")
    c = await make_user(store, 3, "C")
    for u in (a, b):
        await store.groups.join(u, -100)
    await store.groups.join(c, -200)
    for _ in range(3):
        await store.drinks.add(a, 1000, "x")
    await store.drinks.add(b, 5000, "x")
    await store.drinks.add(c, 9000, "x")

    stats = await store.stats.group_stats(-100, 24)
    assert [(u.nick, u.count) for u in stats.top10] == [("A", 3), ("B", 1)]
    assert stats.group_sum.sum == 8000
    assert stats.global_drinks == 5

    alco = await store.stats.group_alcohol_stats(-100, 24)
    assert [(u.nick, u.sum) for u in alco.top10] == [("B", 5000), ("A", 3000)]
    assert alco.group_sum.sum == 8000
    assert alco.global_alcohol == 17000

    empty = await store.stats.group_stats(-999, 24)
    assert empty.top10 == [] and empty.group_sum.sum == 0 and empty.group_sum.first_drink is None


async def test_global_stats(store, clock):
    a = await make_user(store, 1, "A")
    b = await make_user(store, 2, "B")
    await store.groups.join(a, -100)
    await store.drinks.add(a, 1000, "x")
    await store.drinks.add(a, 1000, "x")
    clock.advance(hours=3 * 24)
    await store.drinks.add(b, 1000, "x")
    await store.users.touch(b)
    stats = await store.stats.global_stats()
    assert stats.users == 2
    assert stats.drinks_now == 3 and stats.drinks_total == 3
    assert stats.groups == 1
    assert stats.active_users_1d == 1  # only B has used the bot lately
    assert stats.active_users_7d == 2
    assert [(u.nick, u.count) for u in stats.top10] == [("A", 2), ("B", 1)]
