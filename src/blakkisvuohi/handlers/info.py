"""Commands that print static information: /about /help /komennot /terms /whoami /data"""

from __future__ import annotations

from aiogram.types import BufferedInputFile, Message

from ..access import EVERYONE, PRIVATE, USER, access, cmd
from ..csvexport import to_csv
from ..db import Store
from ..db.models import User
from ..formatting import esc
from ..strings import S
from .common import reply_and_remove_keyboard
from .registry import HandlerSet

router = HandlerSet("info")

# In the order they are listed in /help (admin commands are left out)
COMMAND_DESCRIPTIONS = [
    S.commands.about.cmd_description,
    S.commands.annokset.cmd_description,
    S.commands.data.cmd_description,
    S.commands.help.cmd_description,
    S.commands.jalkikellotus.cmd_description,
    S.commands.juoma.cmd_description,
    S.commands.kalja033.cmd_description,
    S.commands.kalja05.cmd_description,
    S.commands.komennot.cmd_description,
    S.commands.kuvaaja.cmd_description,
    S.commands.laatta.cmd_description,
    S.commands.moro.cmd_description,
    S.commands.poistu.cmd_description,
    S.commands.promillet.cmd_description,
    "/start - KakkosVuohen valikko",
    S.commands.stats.cmd_description,
    S.commands.stats2.cmd_description,
    S.commands.terms.cmd_description,
    S.commands.tunnus.cmd_description,
    S.commands.whoami.cmd_description,
]


def _command_list() -> str:
    return S.commands.blakkis.cmd_list.format(cmd_list="\n".join(COMMAND_DESCRIPTIONS))


@router.message(cmd("about"), flags=access(PRIVATE, EVERYONE))
async def about(message: Message) -> None:
    await message.answer(S.commands.about.text)


@router.message(cmd("help"), flags=access(PRIVATE, EVERYONE))
async def help_(message: Message) -> None:
    await message.answer(S.commands.blakkis.help_text + "\n\n" + _command_list())


@router.message(cmd("komennot"), flags=access(PRIVATE, EVERYONE))
async def commands_list(message: Message) -> None:
    await message.answer(_command_list())


@router.message(cmd("terms"), flags=access(PRIVATE, EVERYONE))
async def terms(message: Message) -> None:
    await message.answer(S.commands.terms.reply)


@router.message(cmd("whoami"), flags=access(PRIVATE, USER))
async def whoami(message: Message, user: User) -> None:
    await message.answer(
        S.commands.whoami.reply.format(
            username=esc(user.nick),
            user_id=user.user_id,
            weight=user.weight,
            height=user.height,
            gender=user.gender,
        )
    )


@router.message(cmd("data"), flags=access(PRIVATE, EVERYONE))
async def data(message: Message, store: Store) -> None:
    """
    Sends everything stored about the user to them as CSV files. Private only, so that the files
    can never end up in a group chat. Available also to users who haven't accepted the terms,
    as their data is still theirs.
    """
    assert message.from_user is not None
    tables = await store.users.export(message.from_user.id)
    if tables.is_empty():
        await reply_and_remove_keyboard(message, S.commands.data.no_data)
        return
    await message.answer(S.commands.data.reply)
    for filename, table in (
        ("user.csv", tables.user),
        ("drinks.csv", tables.drinks),
        ("groups.csv", tables.groups),
    ):
        csv = to_csv(table.columns, table.rows).encode()
        await message.answer_document(BufferedInputFile(csv, filename=filename))
