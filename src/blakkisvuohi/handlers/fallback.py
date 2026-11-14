from __future__ import annotations

from aiogram import F
from aiogram.types import CallbackQuery, Message

from ..access import EVERYONE, PRIVATE, access
from ..strings import S
from ..telegram_utils import safe_answer
from .registry import HandlerSet

router = HandlerSet("fallback")


@router.message(F.chat.type == "private", F.text, flags=access(PRIVATE, EVERYONE))
async def not_understood(message: Message) -> None:
    """Text that no command or question was waiting for. Groups are left alone on purpose."""
    await message.answer(S.commands.blakkis.command_not_found)


@router.callback_query()
async def unknown_button(callback: CallbackQuery) -> None:
    """A button that nothing knows about (very old, or made up): just stop its spinner."""
    await safe_answer(callback)
