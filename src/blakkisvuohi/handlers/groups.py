"""Group commands and the ones that work both in groups and in private: /moro /poistu /promillet
/annokset /stats /stats2 /kuvaaja"""

from __future__ import annotations

import asyncio
import logging
import time

from aiogram.filters import CommandObject
from aiogram.types import BufferedInputFile, Message

from .. import alcomath, charts
from ..access import ANYWHERE, CHAT, USER, access, cmd
from ..config import Settings
from ..db import Store
from ..db.models import GroupMember, User
from ..formatting import esc, rnum
from ..parsing import parse_leading_int
from ..strings import S
from .common import consumption, long_status
from .registry import HandlerSet

log = logging.getLogger("blakkis.commands")
router = HandlerSet("groups")


@router.message(cmd("moro"), flags=access(CHAT, USER))
async def moro(message: Message, store: Store, user: User) -> None:
    await store.groups.join(user, message.chat.id)
    await message.answer(S.commands.moro.join_text.format(chat_title=esc(message.chat.title)))


@router.message(cmd("poistu"), flags=access(CHAT, USER))
async def poistu(message: Message, store: Store, user: User) -> None:
    await store.groups.leave(user, message.chat.id)
    await message.answer(S.commands.poistu.leave_text.format(chat_title=esc(message.chat.title)))


@router.message(cmd("promillet"), flags=access(ANYWHERE, USER))
async def promillet(message: Message, store: Store, user: User, settings: Settings) -> None:
    if message.chat.type == "private":
        await message.answer(await long_status(store, user, settings))
        return
    listing = await store.groups.permilles_listing(message.chat.id)
    lines = [
        S.commands.promillet.text_group_list_item.format(
            username=esc(e.nick),
            permilles=rnum(e.value, 2),
            drinks12h=rnum(e.standard_drinks_12h, 2),
            drinks24h=rnum(e.standard_drinks_24h, 2),
        )
        for e in listing
    ]
    await message.answer(
        S.commands.promillet.text_group.format(
            chat_title=esc(message.chat.title), list="\n".join(lines)
        )
    )


@router.message(cmd("annokset"), flags=access(ANYWHERE, USER))
async def annokset(message: Message, store: Store, user: User, settings: Settings) -> None:
    if message.chat.type == "private":
        await message.answer(await long_status(store, user, settings))
        return
    listing = await store.groups.standard_drinks_listing(message.chat.id)
    lines = [
        S.commands.annokset.text_group_list_item.format(
            username=esc(e.nick),
            standard_drinks=rnum(e.value, 2),
            drinks12h=rnum(e.standard_drinks_12h, 2),
            drinks24h=rnum(e.standard_drinks_24h, 2),
        )
        for e in listing
    ]
    await message.answer(
        S.commands.annokset.text_group.format(
            chat_title=esc(message.chat.title), list="\n".join(lines)
        )
    )


# -- /stats and /stats2 ---------------------------------------------------------------------------


def _requested_days(command: CommandObject, retention_days: int) -> int | None:
    """
    '/stats 3' -> 3. Anything that is not a positive number means 'everything there is'. There is
    nothing older than the retention period, so that is the longest that can be asked for.
    """
    first = command.args.split()[0] if command.args and command.args.split() else None
    days = parse_leading_int(first)
    return min(days, retention_days) if days else None


@router.message(cmd("stats"), flags=access(ANYWHERE, USER))
async def stats(
    message: Message, command: CommandObject, store: Store, user: User, settings: Settings
) -> None:
    days = _requested_days(command, settings.retention_days)
    hours = (days or settings.retention_days) * 24
    if message.chat.type == "private":
        numbers = consumption(
            await store.drinks.sum_for_hours(user, hours), days, store.drinks.now()
        )
        await message.answer(S.commands.stats.private.format(**numbers))
        return
    result = await store.stats.group_stats(message.chat.id, hours)
    top10 = "\n".join(f"{esc(u.nick)} - {u.count}" for u in result.top10)
    await message.answer(
        S.commands.stats.group.format(
            **consumption(result.group_sum, days, store.drinks.now()),
            global_drinks_count=result.global_drinks,
            top10List=top10,
        )
    )


@router.message(cmd("stats2"), flags=access(ANYWHERE, USER))
async def stats2(
    message: Message, command: CommandObject, store: Store, user: User, settings: Settings
) -> None:
    days = _requested_days(command, settings.retention_days)
    hours = (days or settings.retention_days) * 24
    if message.chat.type == "private":
        numbers = consumption(
            await store.drinks.sum_for_hours(user, hours), days, store.drinks.now()
        )
        await message.answer(S.commands.stats2.private.format(**numbers))
        return
    result = await store.stats.group_alcohol_stats(message.chat.id, hours)
    top10 = "\n".join(
        f"{esc(u.nick)} - {rnum(alcomath.to_standard_drinks(u.sum / 1000.0))}" for u in result.top10
    )
    await message.answer(
        S.commands.stats2.group.format(
            **consumption(result.group_sum, days, store.drinks.now()),
            global_drinks_std=rnum(alcomath.to_standard_drinks(result.global_alcohol / 1000.0)),
            top10List=top10,
        )
    )


# -- /kuvaaja -------------------------------------------------------------------------------------

_chart_slots = asyncio.Semaphore(2)  # rendering is CPU heavy, do not let it pile up


@router.message(cmd("kuvaaja"), flags=access(ANYWHERE, USER))
async def kuvaaja(message: Message, store: Store, user: User, settings: Settings) -> None:
    title = S.commands.kuvaaja.graph_title.format(chat_title=message.chat.title or user.nick)
    if message.chat.type == "private":
        drinks = await store.drinks.chart_drinks(user)
        members = (
            {
                user.user_id: GroupMember(
                    user.user_id, user.nick, user.weight, user.gender, user.height, drinks
                )
            }
            if drinks
            else {}
        )
    else:
        members = await store.groups.members_with_drinks(message.chat.id)

    try:
        async with _chart_slots:
            png = await asyncio.to_thread(
                charts.render_chart, list(members.values()), title, time.time(), settings.tzinfo
            )
    except Exception:
        log.exception("Rendering a chart failed")
        await message.answer(S.commands.kuvaaja.img_failed)
        return
    await message.answer_photo(BufferedInputFile(png, filename="kuvaaja.png"), caption=esc(title))
