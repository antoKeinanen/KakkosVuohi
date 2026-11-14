"""Who may do what, and in which chats."""

from aiogram.exceptions import TelegramForbiddenError
from aiogram.methods import SendMessage
from harness import BOT_USERNAME, make_harness

from blakkisvuohi.announcements import ANNOUNCEMENTS
from blakkisvuohi.middlewares import ThrottleMiddleware
from blakkisvuohi.strings import S

STR = S.commands.blakkis


async def test_unregistered_users_are_asked_to_register(h):
    for command in ("/juoma", "/kalja033", "/promillet", "/whoami", "/laatta", "/jalkikellotus"):
        await h.say(command)
        assert h.texts() == [STR.user404], command


async def test_commands_that_do_not_need_an_account(h):
    for command in ("/about", "/help", "/komennot", "/terms", "/tunnus"):
        await h.say(command)
        texts = h.texts()
        assert len(texts) == 1 and texts[0] not in (STR.user404, STR.unauthorized), command


async def test_users_who_have_not_accepted_the_terms_are_sent_to_tunnus(h):
    await h.register()
    await h.revoke_terms()
    await h.say("/kalja033")
    assert h.texts() == [STR.please_update_user_info]
    await h.say("/about")  # commands that do not need an account still work
    assert len(h.texts()) == 1


async def test_private_commands_are_ignored_in_groups_unless_addressed_to_the_bot(h):
    await h.register()
    await h.say("/kalja033", chat=-100, chat_type="group", title="G")
    assert h.new() == []
    assert (await h.store.drinks.last(await h.store.users.find(1))) is None

    await h.say(f"/kalja033@{BOT_USERNAME}", chat=-100, chat_type="group", title="G")
    (sent,) = h.new()
    assert sent.text == STR.use_only_in_private
    assert sent.chat_id == 1  # sent privately, not into the group


async def test_commands_addressed_to_another_bot_are_ignored(h):
    await h.register()
    await h.say("/kalja033@someotherbot")
    assert h.new() == []
    await h.say("/promillet@someotherbot", chat=-100, chat_type="group", title="G")
    assert h.new() == []


async def test_group_commands_are_refused_in_private(h):
    await h.register()
    await h.say("/moro")
    assert h.texts() == [STR.use_only_in_chats]


async def test_admin_commands(h):
    await h.say("/admin_stats", user=5)
    assert h.texts() == [STR.unauthorized]
    await h.register(5)
    await h.say("/admin_stats", user=5)
    assert h.texts() == [STR.unauthorized]
    await h.say("/admin_stats", user=999)  # the admin needs no account
    (text,) = h.texts()
    assert text.startswith("Tilastoja:")
    # admin commands are private only
    await h.say("/admin_stats", user=999, chat=-100, chat_type="group", title="G")
    assert h.new() == []


async def test_admin_commands_are_disabled_without_an_admin(store, tmp_path):
    h = await make_harness(store, tmp_path, admin_id=None)
    await h.say("/admin_stats", user=999)
    assert h.texts() == [STR.unauthorized]


async def test_admin_can_set_log_levels(h):
    import logging

    await h.say("/admin_loglevel db debug", user=999)
    assert logging.getLogger("blakkis.db").level == logging.DEBUG
    assert h.texts() == ["Asetettu 'db' tasoksi 'debug'"]
    await h.say("/admin_loglevel nonsense nonsense", user=999)  # falls back to safe defaults
    assert h.texts() == ["Asetettu 'commands' tasoksi 'info'"]
    logging.getLogger("blakkis.db").setLevel(logging.NOTSET)


async def test_unknown_text_in_private_is_not_understood_but_ignored_in_groups(h):
    await h.say("hello?")
    assert h.texts() == [STR.command_not_found]
    await h.say("/nosuchcommand")
    assert h.texts() == [STR.command_not_found]
    await h.say("hello?", chat=-100, chat_type="group", title="G")
    await h.say("/nosuchcommand", chat=-100, chat_type="group", title="G")
    assert h.new() == []


async def test_messages_from_bots_are_ignored(h):
    await h.say("/about", is_bot=True)
    assert h.new() == []


async def test_new_users_do_not_get_old_announcements_but_existing_ones_get_new_ones_once(h):
    await h.register()
    await h.say("/about")
    assert len(h.texts()) == 1  # no announcements

    await h.store.users.update_read_announcements(
        await h.store.users.find(1), len(ANNOUNCEMENTS) - 2
    )
    await h.say("/about")
    first, second = h.new()
    assert first.text.startswith("Ilmoituksia:")
    assert ANNOUNCEMENTS[-2][:30] in first.text and ANNOUNCEMENTS[-1][:30] in first.text
    await h.say("/about")
    assert len(h.new()) == 1  # shown only once


async def test_announcements_are_retried_when_they_could_not_be_delivered(h):
    """In a group the user may never have started the bot, so the private message fails."""
    await h.register()
    await h.store.users.update_read_announcements(await h.store.users.find(1), 0)
    h.session.fail_with[1] = TelegramForbiddenError(
        method=SendMessage(chat_id=1, text="x"), message="bot can't initiate conversation"
    )
    await h.say("/promillet", chat=-100, chat_type="group", title="G")
    user = await h.store.users.find(1)
    assert user.read_announcements == 0  # not marked as read

    del h.session.fail_with[1]
    h.new()
    await h.say("/about")
    assert any(t.startswith("Ilmoituksia:") for t in h.texts())
    assert (await h.store.users.find(1)).read_announcements == len(ANNOUNCEMENTS)


async def test_flooding_is_throttled(store, tmp_path):
    clock = [0.0]
    h = await make_harness(
        store, tmp_path, throttle=ThrottleMiddleware(rate=1, burst=5, clock=lambda: clock[0])
    )
    for _ in range(20):
        await h.say("/about")
    assert len(h.new()) == 5
    clock[0] += 3  # tokens refill
    await h.say("/about")
    await h.say("/about")
    await h.say("/about")
    await h.say("/about")
    assert len(h.new()) == 3
    # another user is not affected by the flood
    await h.say("/about", user=2)
    assert len(h.new()) == 1
