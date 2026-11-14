from __future__ import annotations

import math
import random
from collections.abc import Sequence

from aiogram.types import (
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from aiogram.types import User as TelegramUser

from .. import alcomath, constants
from ..config import Settings
from ..constants import round_half_up
from ..db import Store
from ..db.models import DrinkSum, User
from ..formatting import drinks_list, hours_and_minutes, num, rnum
from ..strings import S


def nick_of(tg_user: TelegramUser) -> str:
    """The name that is shown in group listings: @username, or the name if there is none."""
    name = tg_user.username
    if not name:
        name = tg_user.first_name
        if tg_user.last_name:
            name += " " + tg_user.last_name
    return name.strip()[:128] or "?"


def short_permilles(ebac: alcomath.EBAC) -> str:
    return S.short_permilles_text.format(
        permilles=rnum(ebac.permilles, 2), permilles30Min=rnum(ebac.permilles_30min, 2)
    )


def drink_response(ebac: alcomath.EBAC) -> str:
    # not security relevant, a random cheer
    return random.choice(S.drink_responses) + "\n\n" + short_permilles(ebac)  # noqa: S311


def reply_keyboard(rows: Sequence[Sequence[str]], *, one_time: bool = False) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=text) for text in row] for row in rows],
        resize_keyboard=True,
        one_time_keyboard=one_time,
    )


async def reply_and_remove_keyboard(message: Message, text: str) -> None:
    await message.answer(text, reply_markup=ReplyKeyboardRemove())


async def long_status(store: Store, user: User, settings: Settings) -> str:
    """The detailed EBAC status of a user, as shown by /promillet and /annokset in private."""
    ebac, drinks72h = await store.drinks.ebac_with_recent(user, 72)
    hours, minutes = hours_and_minutes(ebac.burn_hours)
    return S.long_permilles_text.format(
        permilles=rnum(ebac.permilles, 2),
        permilles30Min=rnum(ebac.permilles_30min, 2),
        grams=rnum(ebac.grams),
        standard_drinks=rnum(alcomath.to_standard_drinks(ebac.grams), 2),
        hours=hours,
        minutes=minutes,
        drinkList72h=drinks_list(drinks72h, settings.tzinfo, with_dates=True),
    )


def consumption(
    drink_sum: DrinkSum, days: int | None, now: float, *, ceil: bool = False
) -> dict[str, str]:
    """
    The numbers of the 'you have drunk X in N days' sentences. `days` is None for 'since the
    first drink', in which case the day count is counted from that drink.
    """
    if days is None:
        first = drink_sum.first_drink
        if first is None:
            days = 0
        else:
            elapsed_days = (now - first) / (24 * constants.HOUR)
            days = math.ceil(elapsed_days) if ceil else round_half_up(elapsed_days)
    grams = drink_sum.sum / 1000.0
    standard_drinks = grams / constants.STANDARD_DRINK_GRAMS
    return {
        "day_count": num(days),
        "grams": rnum(grams, 1),
        "standard_drinks": rnum(standard_drinks, 1),
        # no drinks at all would mean a day count of zero: do not divide by it
        "avg_standard_drinks": rnum(standard_drinks / max(days, 1), 1),
    }
