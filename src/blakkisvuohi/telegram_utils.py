from __future__ import annotations

import logging

from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery

log = logging.getLogger("blakkis.system")


async def safe_answer(callback: CallbackQuery, text: str | None = None, **kwargs: object) -> None:
    """
    Answer a callback query. Telegram refuses to when the button is very old ("query is too old"),
    which is nothing the user or the admin should hear about.
    """
    try:
        await callback.answer(text, **kwargs)  # type: ignore[arg-type]
    except TelegramAPIError as exc:
        log.debug("Could not answer a callback query: %s", exc)
