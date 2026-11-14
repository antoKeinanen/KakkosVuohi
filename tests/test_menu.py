"""The /start menu."""

from aiogram.methods import AnswerCallbackQuery

from blakkisvuohi import constants
from blakkisvuohi.menu.engine import MenuCB
from blakkisvuohi.strings import S

ST = S.commands.start
JUO = ST.juo
ASET = ST.asetukset
LUO = ST.luo_tunnus


async def open_menu(h, user=1):
    await h.say("/start", user=user)
    (sent,) = h.new()
    return sent


async def press(h, button, user=1):
    await h.press(button, user=user)
    return h.new()


# -- who sees what --------------------------------------------------------------------------------


async def test_menu_of_somebody_without_an_account(h):
    sent = await open_menu(h)
    assert sent.text.startswith("🐐 <b>Bäää - KakkosVuohi</b> 🐐")
    assert ST.on_select_nonuser in sent.text
    assert sent.button_rows() == [[LUO.button_text, ST.help.button_text]]


async def test_menu_of_a_user(h):
    await h.register()
    sent = await open_menu(h)
    assert "<b>Nyt:</b> 0‰ - <b>30min:</b> 0‰" in sent.text
    assert "Veressäsi on 0 grammaa alkoholia" in sent.text
    assert sent.button_rows() == [
        [JUO.button_text, ST.tilastoja.button_text],
        [ASET.button_text, ST.help.button_text],
    ]


async def test_a_user_who_has_not_accepted_the_terms_gets_the_menu_of_the_unregistered(h):
    await h.register()
    await h.revoke_terms()
    sent = await open_menu(h)
    assert LUO.button_text in sent.buttons() and JUO.button_text not in sent.buttons()


# -- drinking -------------------------------------------------------------------------------------


async def test_navigating_and_drinking(h, clock):
    await h.register()
    await open_menu(h)

    (juo,) = await press(h, JUO.button_text)
    assert juo.kind == "edit"  # the menu message is edited in place
    assert JUO.on_select in juo.text and "Bäää - Juo" in juo.text
    assert juo.button_rows() == [
        [JUO.miedot.button_text, JUO.viinit.button_text],
        [JUO.shotit.button_text, JUO.oma.button_text],
        [JUO.jalkikellotus.button_text, JUO.kumoa.button_text],
        [S.commands.blakkis.back],
    ]
    (miedot,) = await press(h, JUO.miedot.button_text)
    assert "Bäää - Miedot" in miedot.text
    assert len(miedot.buttons()) == 7 + 1

    (drank,) = await press(h, "🍺 33cl 4.7%")
    assert "Juoma tallennettu." in drank.text
    assert drank.buttons() == miedot.buttons()  # the user stays in the category
    assert "<b>Nyt:</b> 0‰" in drank.text or "<b>Nyt:</b>" in drank.text  # the header is current
    (drink,) = await h.store.drinks.since(await h.store.users.find(1), 1)
    assert (drink.description, drink.alcohol) == ("🍺 33cl 4.7%", constants.KALJA033)

    clock.advance(minutes=20)
    (juo,) = await press(h, S.commands.blakkis.back)  # back to Juo
    assert "Bäää - Juo" in juo.text
    assert "🍺 33cl 4.7%" in juo.buttons()  # a quick pick button for the latest drink
    assert "Viimeisen tunnin tapahtumat" in juo.text

    (again,) = await press(h, "🍺 33cl 4.7%")  # the quick pick
    assert "Juoma tallennettu." in again.text
    assert len(await h.store.drinks.since(await h.store.users.find(1), 1)) == 2

    (root,) = await press(h, S.commands.blakkis.back)
    assert S.commands.blakkis.back not in root.buttons()  # the root has no back button
    assert "Veressäsi on" in root.text


async def test_quick_picks_do_not_offer_late_clocked_drinks(h):
    await h.register()
    user = await h.store.users.find(1)
    await h.store.drinks.add(user, 12000, "Jälkikellotus 33cl 4.7%")
    await h.store.drinks.add(user, 12000, "🍷 12cl 12%")
    await open_menu(h)
    (juo,) = await press(h, JUO.button_text)
    assert "🍷 12cl 12%" in juo.buttons()
    assert not any(b.startswith("Jälkikellotus") for b in juo.buttons())


async def test_own_drink(h):
    await h.register()
    await open_menu(h)
    await press(h, JUO.button_text)
    (oma,) = await press(h, JUO.oma.button_text)
    assert "Kirjoita juoma muodossa senttilitrat prosentit" in oma.text

    help_example = JUO.oma.help_example
    for text, error in [
        ("33", JUO.oma.error_words),
        ("33 5.1 extra", JUO.oma.error_words),
        ("abc 5", JUO.oma.error_cl),
        ("-33 5", JUO.oma.error_cl),
        ("0 5", JUO.oma.error_cl),
        ("33 abc", JUO.oma.error_vol),
        ("33 -5", JUO.oma.error_vol),
        ("33 101%", JUO.oma.error_vol),
        ("500 90", JUO.oma.error_exceeds),
    ]:
        await h.say(text)
        (sent,) = h.new()
        assert error.format(help_example=help_example) in sent.text, text
    assert await h.store.drinks.last(await h.store.users.find(1)) is None

    await h.say("33cl 5,1%")
    (ok,) = h.new()
    assert "Juoma tallennettu." in ok.text
    assert ok.kind == "send"  # text answers are new messages; they still carry the keyboard
    assert S.commands.blakkis.back in ok.buttons()
    (drink,) = await h.store.drinks.since(await h.store.users.find(1), 1)
    assert drink.description == "Oma juoma - 33cl 5.1%"


async def test_late_clocking(h, clock):
    await h.register()
    await open_menu(h)
    await press(h, JUO.button_text)
    (late,) = await press(h, JUO.jalkikellotus.button_text)
    assert JUO.jalkikellotus.save.button_text not in late.buttons()  # nothing to save yet

    await h.say("abc")
    assert JUO.jalkikellotus.hours_error in h.new()[0].text
    await h.say("3")
    assert JUO.jalkikellotus.input_drinks_start in h.new()[0].text
    await h.say("33 4.7 odd")
    assert JUO.jalkikellotus.input_drinks_words_error in h.new()[0].text
    await h.say("33 4.7\n4cl 40%")
    (added,) = h.new()
    assert "2 juoma(a) syötetty" in added.text and "4cl 40%" in added.text
    assert JUO.jalkikellotus.save.button_text in added.buttons()

    (saved,) = await press(h, JUO.jalkikellotus.save.button_text)
    assert "2 juomaa jälkikellotettu onnistuneesti!" in saved.text
    drinks = await h.store.drinks.since(await h.store.users.find(1), 4)
    assert [(d.description, clock.now - d.created) for d in drinks] == [
        ("Jälkikellotus 33cl 4.7%", 10800),
        ("Jälkikellotus 4cl 40%", 0),
    ]
    assert JUO.jalkikellotus.save.button_text not in saved.buttons()  # saved: nothing pending


async def test_leaving_late_clocking_forgets_the_drinks(h):
    await h.register()
    await open_menu(h)
    await press(h, JUO.button_text)
    await press(h, JUO.jalkikellotus.button_text)
    await h.say("2")
    await h.say("33 4.7")
    h.new()
    await press(h, S.commands.blakkis.back)
    (late,) = await press(h, JUO.jalkikellotus.button_text)
    assert JUO.jalkikellotus.save.button_text not in late.buttons()
    await h.say("33 4.7")  # asked for the hours again, so this is an error
    assert JUO.jalkikellotus.hours_error in h.new()[0].text


async def test_undoing_a_drink(h):
    await h.register()
    await open_menu(h)
    (empty,) = await press(h, JUO.button_text)
    (none,) = await press(h, JUO.kumoa.button_text)
    assert JUO.kumoa.on_select_no_drinks in none.text and S.yes not in none.buttons()

    user = await h.store.users.find(1)
    await h.store.drinks.add(user, 12000, "first")
    await h.store.drinks.add(user, 12000, "second")
    (ask,) = await press(h, S.commands.blakkis.back)
    (ask,) = await press(h, JUO.kumoa.button_text)
    assert "<b>Nimi:</b> second" in ask.text and S.yes in ask.buttons()
    (done,) = await press(h, S.yes)
    assert "Kumoaminen onnistui" in done.text
    assert [d.description for d in await h.store.drinks.since(user, 1)] == ["first"]
    assert S.yes not in done.buttons()  # a second tap must not undo another drink
    await h.press(S.yes, data=ask.markup.inline_keyboard[0][0].callback_data)
    assert [d.description for d in await h.store.drinks.since(user, 1)] == ["first"]


# -- statistics -----------------------------------------------------------------------------------


async def test_statistics(h):
    await h.register()
    user = await h.store.users.find(1)
    for _ in range(3):
        await h.store.drinks.add(user, 12000, "beer")
    await open_menu(h)
    (til,) = await press(h, ST.tilastoja.button_text)
    (kulutus,) = await press(h, ST.tilastoja.kulutus.button_text)
    assert "tuhonnut *" not in kulutus.text and "<b>36</b> grammaa" in kulutus.text
    # only ranges within the one week that data is kept for are offered
    assert kulutus.buttons()[:3] == ["1 päivä", "3 päivää", "7 päivää"]
    (seven,) = await press(h, "7 päivää")
    assert "<b>7</b> päivän aikana" in seven.text
    await h.say("30")  # there is nothing older than a week
    assert "<b>7</b> päivän aikana" in h.new()[0].text
    await h.say("nonsense")  # falls back to "all time" like before
    assert len(h.new()) == 1

    await press(h, S.commands.blakkis.back)
    (otinko,) = await press(h, ST.tilastoja.otinko.button_text)
    assert "Viimeisen kolmen vuorokauden tapahtumat" in otinko.text and "beer" in otinko.text


# -- registration ---------------------------------------------------------------------------------


async def test_registering_through_the_menu(h):
    await open_menu(h)
    (luo,) = await press(h, LUO.button_text)
    assert LUO.on_select in luo.text
    await h.say("abc")
    assert LUO.weight_error in h.new()[0].text
    await h.say("85")
    assert LUO.height in h.new()[0].text
    await h.say("300")
    assert LUO.height_error in h.new()[0].text
    await h.say("188")
    (gender,) = h.new()
    assert gender.button_rows() == [["Mies", "Nainen"]]
    await h.say("whatever")  # the old version stored anything here
    (gender_again,) = h.new()
    assert LUO.gender_error in gender_again.text
    await h.say("Mies")
    (terms,) = h.new()
    assert terms.button_rows() == [["Kyllä", "Ei"]]
    await h.say("Ei")
    assert LUO.terms_on_reject in h.new()[0].text
    assert await h.store.users.find(1) is None
    await h.say("Kyllä", username="anto")
    (done,) = h.new()
    assert "Moikka User1!" in done.text or "Moikka anto!" in done.text
    user = await h.store.users.find(1)
    # lowercase gender: the math needs it. Height is stored to the nearest 5 cm.
    assert (user.weight, user.height, user.gender) == (85, 190, "mies")
    assert LUO.button_text not in done.buttons()


# -- settings -------------------------------------------------------------------------------------


async def test_changing_the_account(h):
    await h.register(weight=80, height=180, gender="mies", nick="old")
    await open_menu(h)
    await press(h, ASET.button_text)
    (muokkaa,) = await press(h, ASET.muokkaa.button_text)
    assert "<b>Paino:</b> 80kg" in muokkaa.text and "<b>Nimimerkki:</b> old" in muokkaa.text

    (paino,) = await press(h, ASET.muokkaa.paino.button_text)
    assert "80kg" in paino.text
    await h.say("500")
    assert LUO.weight_error in h.new()[0].text
    await h.say("75")
    assert ASET.muokkaa.paino.on_change in h.new()[0].text
    assert (await h.store.users.find(1)).weight == 75

    await press(h, S.commands.blakkis.back)
    await press(h, ASET.muokkaa.pituus.button_text)
    await h.say("10")  # the old version had a different minimum here than when signing up
    assert LUO.height_error in h.new()[0].text
    await h.say("170")
    h.new()
    assert (await h.store.users.find(1)).height == 170

    await press(h, S.commands.blakkis.back)
    (gender,) = await press(h, ASET.muokkaa.sukupuoli.button_text)
    (changed,) = await press(h, S.gender.female)
    assert ASET.muokkaa.sukupuoli.on_change in changed.text
    assert (await h.store.users.find(1)).gender == "nainen"
    assert ASET.muokkaa.sukupuoli.button_text in changed.buttons()  # went back one level

    (renamed,) = await press(h, ASET.paivita.button_text)  # still in the edit screen
    assert "Nimesi on nyt: <b>User1</b>" in renamed.text
    assert (await h.store.users.find(1)).nick == "User1"


async def test_deleting_the_account(h):
    await h.register()
    user = await h.store.users.find(1)
    await h.store.drinks.add(user, 12000, "beer")
    await open_menu(h)
    await press(h, ASET.button_text)
    (ask,) = await press(h, ASET.poista.button_text)
    assert ASET.poista.on_select in ask.text

    (cancelled,) = await press(h, S.no_1st)
    assert ASET.poista.canceled in cancelled.text
    assert await h.store.users.find(1) is not None

    (sure,) = await press(h, S.yes)
    assert ASET.poista.double_confirm in sure.text
    assert sure.buttons()[:2] == [S.no_1st, S.yes]
    (cancelled,) = await press(h, S.no_1st)
    assert ASET.poista.canceled in cancelled.text
    assert ASET.muokkaa.button_text in cancelled.buttons()  # two levels back
    assert await h.store.users.find(1) is not None

    await press(h, ASET.poista.button_text)
    await press(h, S.yes)
    (gone,) = await press(h, S.yes)
    assert ASET.poista.deleted in gone.text
    assert await h.store.users.find(1) is None
    assert (await h.store.users.export(1)).is_empty()
    # the menu is the one of somebody without an account again
    assert LUO.button_text in gone.buttons() and JUO.button_text not in gone.buttons()
    assert "Nyt:" not in gone.text


# -- help -----------------------------------------------------------------------------------------


async def test_help_pages(h):
    await open_menu(h)
    (helps,) = await press(h, ST.help.button_text)
    assert ST.help.on_select in helps.text
    (general,) = await press(h, ST.help.general.button_text)
    assert "Help: Yleistä" in general.text
    (faq,) = await press(h, ST.help.faq.button_text)
    (koodi,) = await press(h, ST.help.faq.koodi.button_text)
    assert "SQLite" in koodi.text
    await press(h, S.commands.blakkis.back)  # from the FAQ to the help
    (privacy,) = await press(h, ST.help.privacy.button_text)
    assert "HMAC" in privacy.text and "/data" in privacy.text


# -- robustness against stale and forged buttons ---------------------------------------------------


async def test_forged_buttons_cannot_reach_screens_the_user_was_not_offered(h):
    await h.register()
    await open_menu(h)
    # a path that exists, but is not a child of where the user is
    await h.press("x", data=MenuCB(path="start/asetukset/poista/yes/yes").pack())
    (sent,) = h.new()
    assert "Veressäsi on" in sent.text  # nothing happened but showing the current screen
    assert await h.store.users.find(1) is not None
    # paths that do not exist
    for path in ("start/nothing", "", "start/juo/", "a" * 50, "start/../start", "start\x00"):
        await h.press("x", data=MenuCB(path=path).pack())
        h.new()
    # and garbage that is not even callback data of the menu: answered, then ignored
    for data in ("m:start/asetukset/poista/yes/yes", "m:", "m:start/juo:1:2", "garbage", "m:a:b:c"):
        await h.press("x", data=data)
        assert h.new() == []
    assert await h.store.users.find(1) is not None
    assert len(h.api_calls(AnswerCallbackQuery)) >= 5  # every press stops the spinner


async def test_buttons_the_user_may_not_use_do_not_work(h):
    # somebody without an account tries a registered-users-only button
    await open_menu(h)
    await h.press("x", data=MenuCB(path="start/juo").pack())
    (sent,) = h.new()
    assert JUO.on_select not in sent.text
    assert await h.drink_count() == 0


async def test_buttons_do_nothing_for_users_who_were_deleted_meanwhile(h):
    await h.register()
    await open_menu(h)
    await press(h, JUO.button_text)
    await press(h, JUO.miedot.button_text)
    await h.store.users.delete(await h.store.users.find(1))
    (sent,) = await press(h, "🍺 33cl 4.7%")
    assert await h.drink_count() == 0
    assert LUO.button_text in sent.buttons()  # the menu of somebody without an account


async def test_old_buttons_after_a_restart_start_a_fresh_menu(h):
    await h.register()
    await open_menu(h)
    await press(h, JUO.button_text)
    # the bot restarts: the conversation state in memory is gone
    h.dp.fsm.storage.storage.clear()
    (fresh,) = await press(h, JUO.miedot.button_text)
    assert fresh.kind == "send"  # a new message, not an edit of the old one
    assert "Veressäsi on" in fresh.text  # the root


async def test_a_pressed_back_button_of_an_old_screen_only_refreshes(h):
    await h.register()
    await open_menu(h)
    (juo,) = await press(h, JUO.button_text)
    back_button_of_juo = juo.markup.inline_keyboard[-1][-1].callback_data
    await press(h, JUO.miedot.button_text)  # the user moved on
    await h.press("x", data=back_button_of_juo)  # ...and presses an old back button
    (sent,) = h.new()
    assert "Bäää - Miedot" in sent.text  # refreshed where they are, did not go back


async def test_commands_end_the_menu_session(h):
    await h.register()
    await open_menu(h)
    await press(h, JUO.button_text)
    await press(h, JUO.oma.button_text)
    await h.say("/about")
    h.new()
    await h.say("33 5")  # nobody is waiting for it
    assert h.texts() == [S.commands.blakkis.command_not_found]


async def test_answering_a_very_old_button_is_not_an_error(h):
    """Telegram refuses to answer old callback queries; that must not look like a bot error."""
    from aiogram.exceptions import TelegramBadRequest
    from aiogram.methods import AnswerCallbackQuery

    await h.register()
    await open_menu(h)
    original = h.session.make_request

    async def refuse_callback_answers(bot, method, timeout=None):  # noqa: ASYNC109
        if isinstance(method, AnswerCallbackQuery):
            raise TelegramBadRequest(method=method, message="query is too old")
        return await original(bot, method, timeout)

    h.session.make_request = refuse_callback_answers
    await h.press(JUO.button_text)
    sent = h.new()
    assert [s for s in sent if s.text == S.commands.blakkis.error] == []
    assert [s for s in sent if s.chat_id == 999] == []  # the admin is not bothered either
    assert any("Bäää - Juo" in s.text for s in sent)  # and the button still worked
