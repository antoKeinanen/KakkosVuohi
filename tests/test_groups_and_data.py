"""Group commands, statistics, the chart and the data export."""

import csv
import io

from aiogram.methods import SendDocument, SendPhoto

from blakkisvuohi.strings import S

G = {"chat": -100, "chat_type": "supergroup", "title": "Otaniemi <Bois> & co"}
BEER = 12241


async def drink(h, user, times=1, mg=BEER):
    u = await h.store.users.find(user)
    for _ in range(times):
        await h.store.drinks.add(u, mg, "beer")


async def test_joining_and_leaving_a_group(h):
    await h.register(1)
    await h.say("/moro", **G)
    (sent,) = h.new()
    # the chat title is user controlled: it must be escaped
    assert sent.text == "Rippaa rauhassa kera Otaniemi &lt;Bois&gt; &amp; co -kavereiden."
    assert sent.chat_id == -100
    assert (await h.store.db.fetchone("SELECT COUNT(*) FROM users_in_groups"))[0] == 1
    await h.say("/moro", **G)  # again: no error, no duplicate
    assert (await h.store.db.fetchone("SELECT COUNT(*) FROM users_in_groups"))[0] == 1
    await h.say("/poistu", **G)
    assert h.texts()[-1].startswith("Ei enää rippausta")
    assert (await h.store.db.fetchone("SELECT COUNT(*) FROM users_in_groups"))[0] == 0


async def test_joining_requires_an_account(h):
    await h.say("/moro", **G)
    assert h.texts() == [S.commands.blakkis.user404]


async def test_group_permilles_listing(h, clock):
    await h.register(1, nick="Heavy")
    await h.register(2, nick="Light")
    await h.register(3, nick="Sober")
    await h.register(4, nick="Out<b>sider")
    for u in (1, 2, 3):
        await h.say("/moro", user=u, **G)
    await h.say("/moro", user=4, chat=-200, chat_type="group", title="Other")
    await drink(h, 1, 3)
    await drink(h, 2, 1)
    await drink(h, 4, 5)
    h.new()
    clock.advance(minutes=40)

    await h.say("/promillet", user=3, **G)
    (sent,) = h.new()
    lines = sent.text.splitlines()
    assert lines[0] == "Otaniemi &lt;Bois&gt; &amp; co -käyttäjien rippitaso:"
    entries = [line for line in lines if "..." in line and not line.startswith("Käyttäjä")]
    assert [e.split("...")[0] for e in entries] == ["Heavy", "Light"]
    assert "(3.05/3.05)" in entries[0] or "/" in entries[0]
    assert "Sober" not in sent.text and "Out" not in sent.text

    await h.say("/annokset", user=3, **G)
    (sent,) = h.new()
    assert "Heavy..." in sent.text and "Light..." in sent.text
    assert "," not in sent.text.split("\n\n", 1)[1]  # one per line, not a comma separated blob


async def test_nicknames_in_group_listings_cannot_inject_markup(h, clock):
    await h.register(1, nick="<a href='https://evil'>click</a>")
    await h.say("/moro", user=1, **G)
    await drink(h, 1, 2)
    h.new()
    clock.advance(minutes=40)
    await h.say("/promillet", user=1, **G)
    (sent,) = h.new()
    assert "<a href" not in sent.text and "&lt;a href" in sent.text


async def test_private_promillet(h, clock):
    await h.register(1)
    await h.say("/promillet")
    (sent,) = h.new()
    assert "<b>Nyt:</b> 0‰" in sent.text
    await drink(h, 1, 2)
    clock.advance(minutes=45)
    await h.say("/promillet")
    (sent,) = h.new()
    assert "grammaa alkoholia" in sent.text and "beer" in sent.text and "11.11." in sent.text
    await h.say("/annokset")  # the same in private
    assert h.new()[0].text == sent.text


async def test_stats_in_private(h):
    await h.register(1)
    await h.say("/stats")
    assert h.texts()[0].startswith("Olet 0 päivän aikana tuhonnut 0 grammaa")  # no division by zero
    await drink(h, 1, 3)
    await h.say("/stats 7")
    (sent,) = h.new()
    assert sent.text.startswith("Olet 7 päivän aikana tuhonnut 36.7 grammaa")
    assert "3.1 annosta" in sent.text and "0.4 annosta per päivä" in sent.text
    for weird in ("/stats abc", "/stats -5", "/stats 0", "/stats 99999999999", "/stats2 1e9"):
        await h.say(weird)
        assert len(h.new()) == 1, weird
    await h.say("/stats2 7")
    assert h.new()[0].text.startswith("Olet 7 päivän aikana")


async def test_group_stats(h):
    await h.register(1, nick="A")
    await h.register(2, nick="B")
    await h.register(3, nick="Elsewhere")
    for u in (1, 2):
        await h.say("/moro", user=u, **G)
    await drink(h, 1, 3)
    await drink(h, 2, 1, mg=36000)
    await drink(h, 3, 9)
    h.new()

    await h.say("/stats 7", user=1, **G)
    (sent,) = h.new()
    assert "Ryhmän jäsenet ovat 7 päivän aikana tuhonneet" in sent.text
    assert "A - 3\nB - 1" in sent.text
    assert "yhteensä tilastoineet 13 juomaa" in sent.text  # all users globally

    await h.say("/stats2 7", user=1, **G)
    (sent,) = h.new()
    assert "<b>annoksina</b>" in sent.text
    assert "B - 3\nA - 3" in sent.text or "A - 3\nB - 3" in sent.text


async def test_group_stats_with_nobody_in_the_group(h):
    await h.register(1)
    await h.say("/stats", user=1, **G)
    assert "Ryhmän jäsenet ovat 0 päivän aikana" in h.texts()[0]


# -- /kuvaaja -------------------------------------------------------------------------------------


async def test_chart_in_private_and_in_groups(h, clock):
    await h.register(1, nick="A")
    await h.register(2, nick="B")
    await h.say("/kuvaaja")  # nothing to draw yet: still answers
    assert len(h.api_calls(SendPhoto)) == 1
    h.new()
    await drink(h, 1, 3)
    await drink(h, 2, 1)
    for u in (1, 2):
        await h.say("/moro", user=u, **G)
    clock.advance(hours=1)
    await h.say("/kuvaaja")
    await h.say("/kuvaaja", user=2, **G)
    photos = h.api_calls(SendPhoto)
    assert len(photos) == 3
    for photo in photos:
        assert photo.photo.data[:8] == b"\x89PNG\r\n\x1a\n"
    assert "&lt;Bois&gt;" in photos[2].caption  # the title is escaped


# -- /data ----------------------------------------------------------------------------------------


async def test_data_export(h):
    await h.register(1, nick="=cmd|' /C calc'!A0")
    await drink(h, 1, 2)
    await h.say("/moro", **G)
    h.new()
    await h.say("/data")
    assert [t for t in h.texts() if t] == [S.commands.data.reply]
    documents = h.api_calls(SendDocument)
    assert [d.document.filename for d in documents] == ["user.csv", "drinks.csv", "groups.csv"]

    def rows(document):
        raw = document.document.data.decode()
        assert raw.startswith("﻿")  # Excel reads it as UTF-8
        return list(csv.reader(io.StringIO(raw.lstrip("﻿"))))

    user_rows = rows(documents[0])
    assert user_rows[0][:3] == ["user_id", "nick", "weight"]
    assert user_rows[1][1] == "'=cmd|' /C calc'!A0"  # not a live spreadsheet formula
    assert len(rows(documents[1])) == 3  # header + 2 drinks
    assert len(rows(documents[2])) == 2


async def test_data_export_without_data(h):
    await h.say("/data")
    assert h.texts() == [S.commands.data.no_data]
    assert h.api_calls(SendDocument) == []


async def test_data_export_is_private_only_and_works_without_terms(h):
    await h.register(1)
    await h.say("/data", **G)
    assert h.new() == []  # a group chat must never receive somebody's data
    await h.revoke_terms()
    await h.say("/data")
    assert len(h.api_calls(SendDocument)) == 3


async def test_data_only_contains_the_requesting_users_rows(h):
    await h.register(1, nick="Mine")
    await h.register(2, nick="Theirs")
    await drink(h, 2, 4)
    await h.say("/data", user=1)
    documents = h.api_calls(SendDocument)
    assert b"Theirs" not in b"".join(d.document.data for d in documents)
    drinks_csv = documents[1].document.data.decode()
    assert drinks_csv.count("\r\n") == 1  # only the header
