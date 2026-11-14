from __future__ import annotations

import logging

from aiogram.filters import CommandObject
from aiogram.types import Message

from ..access import ADMIN, PRIVATE, access, cmd
from ..db import Store
from ..formatting import esc
from ..strings import S
from .registry import HandlerSet

router = HandlerSet("admin")

_LOGGERS = ("system", "db", "commands")
_LEVELS = {"debug": logging.DEBUG, "info": logging.INFO, "error": logging.ERROR}


@router.message(cmd("admin_stats"), flags=access(PRIVATE, ADMIN))
async def admin_stats(message: Message, store: Store) -> None:
    stats = await store.stats.global_stats()
    top10 = "\n".join(f"{esc(u.nick)} - {u.count}" for u in stats.top10)
    await message.answer(
        S.commands.admin_stats.stats_text.format(
            usersCount=stats.users,
            activeUsers1DayCount=stats.active_users_1d,
            activeUsers7DaysCount=stats.active_users_7d,
            groupsCount=stats.groups,
            drinksNowCount=stats.drinks_now,
            top10List=top10,
            global_drinks_count=stats.drinks_total,
        )
    )


@router.message(cmd("admin_loglevel"), flags=access(PRIVATE, ADMIN))
async def admin_loglevel(message: Message, command: CommandObject) -> None:
    words = (command.args or "").split()
    what = words[0] if words and words[0] in _LOGGERS else "commands"
    level = words[1] if len(words) > 1 and words[1] in _LEVELS else "info"
    logging.getLogger(f"blakkis.{what}").setLevel(_LEVELS[level])
    await message.answer(S.commands.admin_loglevel.level_set_text.format(logger=what, level=level))


@router.message(cmd("admin_purge"), flags=access(PRIVATE, ADMIN))
async def admin_purge(message: Message, store: Store) -> None:
    """Runs the purge right now (it also runs every day at noon)."""
    report = await store.purge()
    await message.answer(
        S.commands.admin_purge.report.format(
            scanned=report.accounts_scanned,
            accounts=report.accounts_deleted,
            drinks=report.drinks_deleted,
            leftovers=report.orphans_removed,
            seconds=round(report.seconds, 1),
        )
    )
