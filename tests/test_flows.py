"""The multi-step commands: /tunnus /juoma /jalkikellotus /laatta and the quick drinks."""

import pytest

from blakkisvuohi import constants
from blakkisvuohi.strings import S

T = S.commands.tunnus
J = S.commands.juoma
JK = S.commands.jalkikellotus


# -- /tunnus --------------------------------------------------------------------------------------


async def test_signing_up(h):
    await h.say("/tunnus", username="anto")
    assert h.texts() == [T.start]
    await h.say("80")
    assert h.texts() == [T.height]
    await h.say("182")
    (gender,) = h.new()
    assert gender.text == T.gender and gender.button_rows() == [["Mies", "Nainen"]]
    await h.say("Mies")
    (terms,) = h.new()
    assert "Käyttöehdot" in terms.text and terms.button_rows() == [["Kyllä", "En"]]
    await h.say("Kyllä")
    (done,) = h.new()
    assert done.text == T.new_user.format(username="anto")

    user = await h.store.users.find(1)
    assert (user.nick, user.weight, user.height, user.gender, user.read_terms) == (
        "anto",
        80,
        180,  # stored to the nearest 5 cm
        "mies",
        True,
    )
    # and the conversation is over
    await h.say("80")
    assert h.texts() == [S.commands.blakkis.command_not_found]


async def test_signing_up_validates_every_answer(h):
    await h.say("/tunnus")
    h.new()
    for bad in ("abc", "19", "251", "-80", "80.5", "1e2", "", "８０"):
        if not bad:
            continue
        await h.say(bad)
        assert h.texts() == [T.start_error], bad
    await h.say("80")
    h.new()
    for bad in ("119", "241", "abc", "1.8"):
        await h.say(bad)
        assert h.texts() == [T.height_error], bad
    await h.say("180")
    h.new()
    await h.say("something else")
    (sent,) = h.new()
    assert sent.text == T.gender_error
    await h.say("NAINEN")  # case does not matter
    h.new()
    await h.say("maybe")
    assert h.texts() == [T.terms_error]
    await h.say("En")
    assert h.texts() == [T.terms_on_reject]
    assert await h.store.users.find(1) is None  # nothing was stored without consent


async def test_updating_an_existing_account_keeps_the_history(h):
    await h.register(1, weight=70, nick="old")
    user = await h.store.users.find(1)
    await h.store.drinks.add(user, 12000, "beer")
    for answer in ("/tunnus", "90", "190", "nainen", "kyllä"):
        await h.say(answer, username="newnick")
    assert h.texts()[-1] == T.update
    user = await h.store.users.find(1)
    assert (user.weight, user.height, user.gender, user.nick) == (90, 190, "nainen", "newnick")
    assert len(await h.store.drinks.since(user, 24)) == 1


async def test_nicknames_cannot_inject_markup(h):
    await h.say("/tunnus", first_name="<b>Evil</b> &", username=None)
    for answer in ("80", "180", "mies", "kyllä"):
        await h.say(answer, first_name="<b>Evil</b> &")
    done = h.new()[-1]
    assert "&lt;b&gt;Evil&lt;/b&gt; &amp;" in done.text
    assert "<b>Evil</b>" not in done.text


async def test_a_command_interrupts_a_conversation(h):
    await h.register()
    await h.say("/juoma")
    await h.say("Miedot")
    h.new()
    await h.say("/kalja033")  # works in the middle of /juoma
    (sent,) = h.new()
    assert "Nyt:" in sent.text
    await h.say("🍺 33cl 4.7%")  # the /juoma conversation is gone
    assert h.texts() == [S.commands.blakkis.command_not_found]


# -- quick drinks ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("command", "milligrams"),
    [("/kalja033", constants.KALJA033), ("/kalja05", constants.KALJA05)],
)
async def test_quick_beers(h, command, milligrams):
    await h.register()
    await h.say(command)
    (sent,) = h.new()
    assert "<b>Nyt:</b>" in sent.text and "‰" in sent.text
    (drink,) = await h.store.drinks.since(await h.store.users.find(1), 1)
    assert (drink.alcohol, drink.description) == (milligrams, command)


# -- /juoma ---------------------------------------------------------------------------------------


async def test_juoma_mild_drinks(h):
    await h.register()
    await h.say("/juoma")
    (start,) = h.new()
    assert start.text == J.start and start.button_rows() == [["Miedot", "Tiukat", "Oma"]]
    await h.say("miedot")  # case insensitive
    (menu,) = h.new()
    assert menu.text == J.choose_mild and "🍺 33cl 4.7%" in menu.buttons()
    await h.say("Alkuun")  # back to the start
    assert h.texts() == [J.start]
    await h.say("Miedot")
    h.new()
    await h.say("something I made up")
    assert h.texts() == [J.choose_mild]
    await h.say("🍷 16cl 12%")
    (saved,) = h.new()
    assert "<b>Nyt:</b>" in saved.text
    (drink,) = await h.store.drinks.since(await h.store.users.find(1), 1)
    assert drink.description == "🍷 16cl 12%" and drink.alcohol == constants.MILDS["wine16"].mg


async def test_juoma_strong_drinks(h):
    await h.register()
    await h.say("/juoma")
    await h.say("Tiukat")
    h.new()
    await h.say("40% 4cl")
    h.new()
    (drink,) = await h.store.drinks.since(await h.store.users.find(1), 1)
    assert drink.alcohol == constants.BOOZE["basic"].mg


async def test_juoma_own_drink(h):
    await h.register()
    await h.say("/juoma")
    h.new()
    await h.say("Oma")
    assert h.texts() == [J.self_define_vol]
    for bad in ("abc", "0", "100", "-5", "nan", "1e1"):
        await h.say(bad)
        assert h.texts() == [J.self_define_vol], bad
    await h.say("5,5")  # decimal comma
    assert h.texts() == [J.self_define_cl]
    for bad in ("abc", "0", "-33", "3.5"):
        await h.say(bad)
        assert h.texts() == [J.self_define_cl], bad
    await h.say("33")
    h.new()
    (drink,) = await h.store.drinks.since(await h.store.users.find(1), 1)
    assert drink.description == "Oma juoma - 33cl 5.5%"
    assert drink.alcohol == constants.calc_alcohol_milligrams(0.055, 0.33)


async def test_juoma_own_drink_over_the_limit_is_refused(h):
    await h.register()
    await h.say("/juoma")
    await h.say("Oma")
    await h.say("90")
    await h.say("100")
    assert h.texts()[-1] == J.self_define_error_alcohol_limit
    assert await h.store.drinks.last(await h.store.users.find(1)) is None


# -- /jalkikellotus -------------------------------------------------------------------------------


async def test_jalkikellotus(h, clock):
    await h.register()
    await h.say("/jalkikellotus")
    assert h.texts() == [JK.start]
    for bad in ("0", "24", "-1", "abc"):
        await h.say(bad)
        assert h.texts() == [JK.hours_error], bad
    await h.say("2,5")
    assert h.texts() == [JK.input_drinks_start]

    await h.say("33 4.7")
    assert h.texts() == [JK.input_drinks_drink_saved, JK.input_drinks_start]
    await h.say("33 4.7 5")  # an odd number of words
    assert h.texts() == [JK.input_drinks_error]
    await h.say("33 abc")
    assert h.texts() == [JK.input_drinks_drink_error.format(drink=1)]
    await h.say("33 4.7 0 5")  # the second drink is nonsense
    assert h.texts() == [JK.input_drinks_drink_error.format(drink=2)]
    await h.say("500 100")  # more alcohol than a bottle of sparkling wine
    assert h.texts() == [JK.error_out_of_limits.format(drink=1)]
    await h.say("4 40\n4 40")  # several on separate lines
    assert h.texts() == [JK.input_drinks_drink_saved, JK.input_drinks_start]
    await h.say("STOP")
    (done,) = h.new()
    assert "<b>Nyt:</b>" in done.text

    user = await h.store.users.find(1)
    drinks = await h.store.drinks.since(user, 5)
    assert [d.description for d in drinks] == [
        "Jälkikellotus 33cl 4.7%",
        "Jälkikellotus 4cl 40%",
        "Jälkikellotus 4cl 40%",
    ]
    # spread evenly over the 2.5 hours
    assert [clock.now - d.created for d in drinks] == [9000, 4500, 0]


async def test_jalkikellotus_limits_the_number_of_drinks(h):
    await h.register()
    await h.say("/jalkikellotus")
    await h.say("5")
    h.new()
    await h.say(" ".join(["33 4.7"] * 51))  # one message with too many
    assert h.texts() == [JK.input_drinks_error]
    for _ in range(5):
        await h.say(" ".join(["33 4.7"] * 10))
    h.new()
    await h.say("33 4.7")
    assert h.texts() == [JK.too_many_drinks]


async def test_jalkikellotus_without_drinks_just_ends(h):
    await h.register()
    await h.say("/jalkikellotus")
    await h.say("1")
    await h.say("stop")
    assert "<b>Nyt:</b>" in h.texts()[-1]
    assert await h.store.drinks.last(await h.store.users.find(1)) is None


# -- /laatta --------------------------------------------------------------------------------------


async def test_laatta(h):
    await h.register()
    user = await h.store.users.find(1)
    await h.store.drinks.add(user, 12000, "first")
    await h.store.drinks.add(user, 12000, "second")

    await h.say("/laatta")
    (ask,) = h.new()
    assert ask.text == S.commands.laatta.start_text and ask.button_rows() == [["Kyllä", "En"]]
    await h.say("perhaps")
    assert h.texts() == [S.commands.laatta.error_text]
    await h.say("En")
    assert h.texts() == [S.commands.laatta.cancel]
    assert len(await h.store.drinks.since(user, 1)) == 2

    await h.say("/laatta")
    h.new()
    await h.say("Kyllä")
    assert h.texts()[0].startswith("Laatta onnistui.")
    assert [d.description for d in await h.store.drinks.since(user, 1)] == ["first"]


# -- inputs that are not text ---------------------------------------------------------------------


async def test_overlong_messages_are_not_valid_input(h):
    await h.register()
    await h.say("/jalkikellotus")
    h.new()
    await h.say("1" * 5000)
    assert h.texts() == [S.commands.blakkis.command_not_found]  # nobody was waiting for it
