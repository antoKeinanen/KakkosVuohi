"""Drinking: /kalja033 /kalja05 /juoma /jalkikellotus /laatta"""

from __future__ import annotations

from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ReplyKeyboardRemove

from .. import constants
from ..access import PRIVATE, USER, access, cmd
from ..db import LateDrink, Store, TooManyDrinks
from ..db.models import User
from ..drinkinput import MAX_LATE_DRINKS, DrinkInputError, milligrams
from ..formatting import num, rnum
from ..parsing import MAX_TEXT_LENGTH, parse_float, parse_int
from ..strings import S
from .common import drink_response, reply_and_remove_keyboard, reply_keyboard
from .registry import HandlerSet
from .states import Jalkikellotus, Juoma, Laatta

router = HandlerSet("drinks")
flows = HandlerSet(  # the answers to the questions of the commands
    "drinks-flows",
    message_filters=(F.chat.type == "private", F.text, F.text.len() <= MAX_TEXT_LENGTH),
)

PRIVATE_USER = access(PRIVATE, USER)


async def _save_drink(
    message: Message, store: Store, user: User, milligrams_: int, description: str
) -> None:
    try:
        await store.drinks.add(user, milligrams_, description)
    except TooManyDrinks:
        await reply_and_remove_keyboard(message, S.commands.blakkis.error)
        return
    await reply_and_remove_keyboard(message, drink_response(await store.drinks.ebac(user)))


# -- /kalja033 and /kalja05 -----------------------------------------------------------------------


@router.message(cmd("kalja033"), flags=PRIVATE_USER)
async def kalja033(message: Message, state: FSMContext, store: Store, user: User) -> None:
    await state.clear()
    await _save_drink(message, store, user, constants.KALJA033, "/kalja033")


@router.message(cmd("kalja05"), flags=PRIVATE_USER)
async def kalja05(message: Message, state: FSMContext, store: Store, user: User) -> None:
    await state.clear()
    await _save_drink(message, store, user, constants.KALJA05, "/kalja05")


# -- /juoma ---------------------------------------------------------------------------------------

_TO_START = S.commands.juoma.to_start
_START_KEYBOARD = [[S.commands.juoma.milds, S.commands.juoma.booze, S.commands.juoma.self_define]]
_MILDS_KEYBOARD = [
    [
        constants.MILDS["beercan"].name,
        constants.MILDS["beer4"].name,
        constants.MILDS["beer05"].name,
    ],
    [
        constants.MILDS["beer04"].name,
        constants.MILDS["beerpint"].name,
        constants.MILDS["lonkero"].name,
    ],
    [constants.MILDS["wine12"].name, constants.MILDS["wine16"].name, _TO_START],
]
_BOOZE_KEYBOARD = [
    [
        constants.BOOZE["mild"].name,
        constants.BOOZE["medium"].name,
        constants.BOOZE["basic"].name,
        _TO_START,
    ]
]


def _lookup(text: str, keyboard: list[list[str]]) -> str | None:
    wanted = text.strip().lower()
    for row in keyboard:
        for label in row:
            if label.lower() == wanted:
                return label
    return None


async def _ask_start(message: Message, state: FSMContext, text: str) -> None:
    await state.set_state(Juoma.start)
    await message.answer(text, reply_markup=reply_keyboard(_START_KEYBOARD))


@router.message(cmd("juoma"), flags=PRIVATE_USER)
async def juoma(message: Message, state: FSMContext) -> None:
    await state.clear()
    await _ask_start(message, state, S.commands.juoma.start)


@flows.message(Juoma.start, flags=PRIVATE_USER)
async def juoma_start(message: Message, state: FSMContext) -> None:
    choice = _lookup(message.text or "", _START_KEYBOARD)
    if choice is None:
        await _ask_start(message, state, S.commands.juoma.start_error)
    elif choice == S.commands.juoma.milds:
        await state.set_state(Juoma.miedot)
        await message.answer(
            S.commands.juoma.choose_mild, reply_markup=reply_keyboard(_MILDS_KEYBOARD)
        )
    elif choice == S.commands.juoma.booze:
        await state.set_state(Juoma.tiukat)
        await message.answer(
            S.commands.juoma.choose_booze, reply_markup=reply_keyboard(_BOOZE_KEYBOARD)
        )
    else:
        await state.set_state(Juoma.oma)
        await message.answer(S.commands.juoma.self_define_vol, reply_markup=ReplyKeyboardRemove())


async def _pick_drink(
    message: Message,
    state: FSMContext,
    store: Store,
    user: User,
    keyboard: list[list[str]],
    drinks: dict[str, constants.Drink],
    prompt: str,
) -> None:
    choice = _lookup(message.text or "", keyboard)
    if choice is None:
        await message.answer(prompt, reply_markup=reply_keyboard(keyboard))
    elif choice == _TO_START:
        await _ask_start(message, state, S.commands.juoma.start)
    else:
        drink = next(d for d in drinks.values() if d.name == choice)
        await state.clear()
        await _save_drink(message, store, user, drink.mg, drink.name)


@flows.message(Juoma.miedot, flags=PRIVATE_USER)
async def juoma_miedot(message: Message, state: FSMContext, store: Store, user: User) -> None:
    await _pick_drink(
        message, state, store, user, _MILDS_KEYBOARD, constants.MILDS, S.commands.juoma.choose_mild
    )


@flows.message(Juoma.tiukat, flags=PRIVATE_USER)
async def juoma_tiukat(message: Message, state: FSMContext, store: Store, user: User) -> None:
    await _pick_drink(
        message, state, store, user, _BOOZE_KEYBOARD, constants.BOOZE, S.commands.juoma.choose_booze
    )


@flows.message(Juoma.oma, flags=PRIVATE_USER)
async def juoma_oma(message: Message, state: FSMContext) -> None:
    words = (message.text or "").split()
    vol = parse_float(words[0] if words else None)
    if vol is None or not 0 < vol < 100:
        await message.answer(S.commands.juoma.self_define_vol)
        return
    await state.update_data(vol=vol)
    await state.set_state(Juoma.omacl)
    await message.answer(S.commands.juoma.self_define_cl)


@flows.message(Juoma.omacl, flags=PRIVATE_USER)
async def juoma_omacl(message: Message, state: FSMContext, store: Store, user: User) -> None:
    words = (message.text or "").split()
    cl = parse_int(words[0] if words else None)
    if cl is None or cl <= 0:
        await message.answer(S.commands.juoma.self_define_cl)
        return
    vol = (await state.get_data())["vol"]
    mg = milligrams(cl, vol)
    await state.clear()
    if isinstance(mg, DrinkInputError):
        await reply_and_remove_keyboard(message, S.commands.juoma.self_define_error_alcohol_limit)
        return
    await _save_drink(message, store, user, mg, f"Oma juoma - {cl}cl {num(vol)}%")


# -- /jalkikellotus -------------------------------------------------------------------------------


@router.message(cmd("jalkikellotus"), flags=PRIVATE_USER)
async def jalkikellotus(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(Jalkikellotus.hours)
    await message.answer(S.commands.jalkikellotus.start, reply_markup=ReplyKeyboardRemove())


@flows.message(Jalkikellotus.hours, flags=PRIVATE_USER)
async def jalkikellotus_hours(message: Message, state: FSMContext) -> None:
    words = (message.text or "").split()
    hours = parse_float(words[0] if words else None)
    if hours is None or not 0 < hours < 24:
        await message.answer(S.commands.jalkikellotus.hours_error)
        return
    await state.update_data(hours=hours, drinks=[])
    await state.set_state(Jalkikellotus.drinks)
    await message.answer(S.commands.jalkikellotus.input_drinks_start)


@flows.message(Jalkikellotus.drinks, flags=PRIVATE_USER)
async def jalkikellotus_drinks(
    message: Message, state: FSMContext, store: Store, user: User
) -> None:
    words = (message.text or "").split()
    if not words:
        await message.answer(S.commands.jalkikellotus.input_drinks_error)
        return

    data = await state.get_data()
    drinks: list[list[float]] = data["drinks"]

    if words[0].lower() == "stop":
        late = [
            LateDrink(
                f"{S.commands.jalkikellotus.drink_name} {num(cl)}cl {num(vol)}%",
                int(constants.calc_alcohol_milligrams(vol / 100, cl / 100)),
            )
            for cl, vol in drinks
        ]
        await state.clear()
        try:
            await store.drinks.add_late(user, late, data["hours"])
        except TooManyDrinks:
            await reply_and_remove_keyboard(message, S.commands.blakkis.error)
            return
        await reply_and_remove_keyboard(message, drink_response(await store.drinks.ebac(user)))
        return

    if len(words) < 2 or len(words) % 2 != 0 or len(words) > 2 * MAX_LATE_DRINKS:
        await message.answer(S.commands.jalkikellotus.input_drinks_error)
        return

    parsed: list[list[float]] = []
    for number, i in enumerate(range(0, len(words), 2), start=1):
        cl, vol = parse_float(words[i]), parse_float(words[i + 1])
        result = milligrams(cl, vol)
        if result is DrinkInputError.INVALID:
            await message.answer(
                S.commands.jalkikellotus.input_drinks_drink_error.format(drink=number)
            )
            return
        if result is DrinkInputError.OUT_OF_LIMITS:
            await message.answer(S.commands.jalkikellotus.error_out_of_limits.format(drink=number))
            return
        parsed.append([cl, vol])  # type: ignore[list-item]

    if len(drinks) + len(parsed) > MAX_LATE_DRINKS:
        await message.answer(S.commands.jalkikellotus.too_many_drinks)
        return
    await state.update_data(drinks=drinks + parsed)
    await message.answer(S.commands.jalkikellotus.input_drinks_drink_saved)
    await message.answer(S.commands.jalkikellotus.input_drinks_start)


# -- /laatta --------------------------------------------------------------------------------------

_YES, _NO = S.commands.laatta.start_answer_yes, S.commands.laatta.start_answer_no


@router.message(cmd("laatta"), flags=PRIVATE_USER)
async def laatta(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(Laatta.confirm)
    await message.answer(S.commands.laatta.start_text, reply_markup=reply_keyboard([[_YES, _NO]]))


@flows.message(Laatta.confirm, flags=PRIVATE_USER)
async def laatta_confirm(message: Message, state: FSMContext, store: Store, user: User) -> None:
    answer = (message.text or "").strip().lower()
    if answer == _YES.lower():
        await state.clear()
        await store.drinks.undo_last(user)
        ebac = await store.drinks.ebac(user)
        await reply_and_remove_keyboard(
            message,
            S.commands.laatta.success.format(
                permilles=rnum(ebac.permilles, 2),
                permilles30Min=rnum(ebac.permilles_30min, 2),
            ),
        )
    elif answer == _NO.lower():
        await state.clear()
        await reply_and_remove_keyboard(message, S.commands.laatta.cancel)
    else:
        await message.answer(
            S.commands.laatta.error_text, reply_markup=reply_keyboard([[_YES, _NO]])
        )
