"""Glue between Telegram and the /start menu (menu/engine.py, menu/tree.py)."""

from __future__ import annotations

import logging

from aiogram import F
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.types import User as TelegramUser

from ..access import EVERYONE, PRIVATE, access, cmd
from ..config import Settings
from ..db import Store
from ..db.models import User
from ..menu.engine import MenuCB, MenuContext, Screen
from ..menu.tree import MENU
from ..parsing import MAX_TEXT_LENGTH
from ..telegram_utils import safe_answer
from .common import reply_keyboard
from .registry import HandlerSet
from .states import Menu

log = logging.getLogger("blakkis.commands")

router = HandlerSet("menu")
flows = HandlerSet("menu-flows")

PRIVATE_ALL = access(PRIVATE, EVERYONE)  # the menu adapts itself to who is using it


async def _context(
    state: FSMContext,
    store: Store,
    settings: Settings,
    user: User | None,
    tg_user: TelegramUser,
    text: str | None = None,
) -> tuple[MenuContext, bool]:
    """The menu context of the user, and whether they were in the middle of a menu session."""
    node = None
    variables: dict = {}
    if await state.get_state() == Menu.active.state:
        data = await state.get_data()
        node = MENU.find(data.get("menu_node"))
        variables = data.get("menu_vars") or {}
    # somebody who has not accepted the terms is offered the menu of those without an account
    effective = user if user is not None and user.read_terms else None
    ctx = MenuContext(store, settings, effective, tg_user, node or MENU.root, variables, text)
    return ctx, node is not None


async def _save(state: FSMContext, ctx: MenuContext) -> None:
    await state.set_state(Menu.active)
    await state.update_data(menu_node=ctx.state.path, menu_vars=ctx.vars)


async def _send(message: Message, screen: Screen) -> None:
    markup = (
        reply_keyboard(screen.reply_keyboard, one_time=True)
        if screen.reply_keyboard
        else screen.keyboard
    )
    await message.answer(screen.text, reply_markup=markup)


async def _show(callback: CallbackQuery, screen: Screen) -> None:
    """Edit the message whose button was pressed, or send a new one when that is not possible."""
    message = callback.message
    if isinstance(message, Message) and not screen.reply_keyboard:
        try:
            await message.edit_text(screen.text, reply_markup=screen.keyboard)
            return
        except TelegramBadRequest as exc:
            if "message is not modified" in str(exc):
                return
            log.info("Could not edit a menu message, sending a new one: %s", exc)
    await callback.bot.send_message(  # type: ignore[union-attr]
        callback.from_user.id,
        screen.text,
        reply_markup=reply_keyboard(screen.reply_keyboard, one_time=True)
        if screen.reply_keyboard
        else screen.keyboard,
    )


@router.message(cmd("start"), flags=PRIVATE_ALL)
async def start(
    message: Message, state: FSMContext, store: Store, settings: Settings, user: User | None
) -> None:
    assert message.from_user is not None
    await state.clear()
    ctx, _ = await _context(state, store, settings, user, message.from_user)
    screen = await MENU.root.select(ctx)
    await _save(state, ctx)
    await _send(message, screen)


@flows.callback_query(MenuCB.filter(), flags=PRIVATE_ALL)
async def menu_button(
    callback: CallbackQuery,
    callback_data: MenuCB,
    state: FSMContext,
    store: Store,
    settings: Settings,
    user: User | None,
) -> None:
    await safe_answer(callback)  # stops the spinner of the button right away
    ctx, in_session = await _context(state, store, settings, user, callback.from_user)

    if not in_session:
        # e.g. the bot has restarted since the menu was opened, or another command was used in
        # between: start from the beginning, in a new message
        await state.clear()
        ctx, _ = await _context(state, store, settings, user, callback.from_user)
        screen = await MENU.root.select(ctx)
        await _save(state, ctx)
        await _show_new(callback, screen)
        return

    current = ctx.state
    target = None
    if current.is_available(ctx):
        if callback_data.back:
            target = current.parent if callback_data.path == current.path else None
        else:
            candidate = MENU.find(callback_data.path)
            # only the children of where the user is are reachable: never trust the button
            if candidate is not None and candidate.parent is current:
                target = candidate
        if target is not None and not target.is_available(ctx):
            target = None
    else:
        # the screen is not meant for this user any more (e.g. the account was deleted)
        ctx.state = MENU.root
        current = MENU.root

    if target is None:
        screen = await current.select(ctx)  # a stale button: just show where the user is
    else:
        await current.exit(ctx, target)
        screen = await target.select(ctx)
    await _save(state, ctx)
    await _show(callback, screen)


async def _show_new(callback: CallbackQuery, screen: Screen) -> None:
    await callback.bot.send_message(  # type: ignore[union-attr]
        callback.from_user.id, screen.text, reply_markup=screen.keyboard
    )


@flows.message(
    Menu.active,
    F.chat.type == "private",
    F.text,
    F.text.len() <= MAX_TEXT_LENGTH,
    flags=PRIVATE_ALL,
)
async def menu_text(
    message: Message, state: FSMContext, store: Store, settings: Settings, user: User | None
) -> None:
    assert message.from_user is not None
    ctx, _ = await _context(state, store, settings, user, message.from_user, message.text)
    node = ctx.state
    if node.is_available(ctx):
        screen = await node.handle_text(ctx)
        if screen is None:
            return  # the screen does not ask for text
    else:
        ctx.state = MENU.root
        screen = await MENU.root.select(ctx)
    await _save(state, ctx)
    await _send(message, screen)
