"""/tunnus - sign up, or change the details of the account"""

from __future__ import annotations

from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ReplyKeyboardRemove

from .. import constants
from ..access import EVERYONE, PRIVATE, access, cmd
from ..db import Store
from ..formatting import esc
from ..parsing import MAX_TEXT_LENGTH, in_range, parse_int
from ..strings import S
from .common import nick_of, reply_and_remove_keyboard, reply_keyboard
from .registry import HandlerSet
from .states import Tunnus

router = HandlerSet("account")
flows = HandlerSet(
    "account-flows",
    message_filters=(F.chat.type == "private", F.text, F.text.len() <= MAX_TEXT_LENGTH),
)

PRIVATE_ALL = access(PRIVATE, EVERYONE)  # also for those who do not have an account yet
_GENDERS = [[S.gender.male, S.gender.female]]
_TERMS = [[S.commands.tunnus.terms_answer_yes, S.commands.tunnus.terms_answer_no]]


@router.message(cmd("tunnus"), flags=PRIVATE_ALL)
async def tunnus(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(Tunnus.weight)
    await message.answer(S.commands.tunnus.start, reply_markup=ReplyKeyboardRemove())


@flows.message(Tunnus.weight, flags=PRIVATE_ALL)
async def tunnus_weight(message: Message, state: FSMContext) -> None:
    weight = parse_int(message.text)
    if weight is None or not in_range(weight, *constants.WEIGHT_RANGE):
        await message.answer(S.commands.tunnus.start_error)
        return
    await state.update_data(weight=weight)
    await state.set_state(Tunnus.height)
    await message.answer(S.commands.tunnus.height)


@flows.message(Tunnus.height, flags=PRIVATE_ALL)
async def tunnus_height(message: Message, state: FSMContext) -> None:
    height = parse_int(message.text)
    if height is None or not in_range(height, *constants.HEIGHT_RANGE):
        await message.answer(S.commands.tunnus.height_error)
        return
    await state.update_data(height=height)
    await state.set_state(Tunnus.gender)
    await message.answer(S.commands.tunnus.gender, reply_markup=reply_keyboard(_GENDERS))


@flows.message(Tunnus.gender, flags=PRIVATE_ALL)
async def tunnus_gender(message: Message, state: FSMContext) -> None:
    gender = (message.text or "").strip().lower()
    if gender not in (constants.GENDER_MALE, constants.GENDER_FEMALE):
        await message.answer(S.commands.tunnus.gender_error, reply_markup=reply_keyboard(_GENDERS))
        return
    await state.update_data(gender=gender)
    await state.set_state(Tunnus.terms)
    await message.answer(
        S.commands.tunnus.terms.format(terms=S.commands.terms.reply),
        reply_markup=reply_keyboard(_TERMS),
    )


@flows.message(Tunnus.terms, flags=PRIVATE_ALL)
async def tunnus_terms(message: Message, state: FSMContext, store: Store) -> None:
    assert message.from_user is not None
    answer = (message.text or "").strip().lower()
    if answer == S.commands.tunnus.terms_answer_no.lower():
        await state.clear()
        await reply_and_remove_keyboard(message, S.commands.tunnus.terms_on_reject)
        return
    if answer != S.commands.tunnus.terms_answer_yes.lower():
        await message.answer(S.commands.tunnus.terms_error, reply_markup=reply_keyboard(_TERMS))
        return

    data = await state.get_data()
    await state.clear()
    user, created = await store.users.create_or_update(
        message.from_user.id,
        nick_of(message.from_user),
        data["weight"],
        data["gender"],
        data["height"],
    )
    text = (
        S.commands.tunnus.new_user.format(username=esc(user.nick))
        if created
        else S.commands.tunnus.update
    )
    await reply_and_remove_keyboard(message, text)
