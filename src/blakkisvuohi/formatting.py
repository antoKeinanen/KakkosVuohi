"""Helpers to turn numbers, times and drink lists into text."""

from __future__ import annotations

import html
import math
from collections.abc import Iterable, Sequence
from datetime import datetime, tzinfo
from typing import Protocol

from .constants import round_half_up


class _HasDrinkInfo(Protocol):
    description: str | None
    created: int


def esc(value: object) -> str:
    """Escape user controlled text for Telegram's HTML parse mode. Always use on untrusted input."""
    return html.escape(str(value), quote=False)


def round_to(value: float, decimals: int = 0) -> float:
    factor = 10**decimals
    return round_half_up(value * factor) / factor


def num(value: float) -> str:
    """Print a number the way the previous version did: 12.0 -> '12', 0.35 -> '0.35'."""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def rnum(value: float, decimals: int = 0) -> str:
    return num(round_to(value, decimals))


def two_digits(value: int) -> str:
    # ('0' + n).slice(-2) of the previous version: 5 -> '05', 60 -> '60'
    return ("0" + str(value))[-2:]


def hours_and_minutes(burn_hours: float) -> tuple[int, str]:
    hours = math.floor(burn_hours)
    return hours, two_digits(math.ceil((burn_hours - hours) * 60))


def format_datetime(timestamp: float, tz: tzinfo) -> str:
    dt = datetime.fromtimestamp(timestamp, tz)
    return f"{dt.day}.{dt.month}.{dt.year} {dt:%H:%M}"


def drinks_list(
    drinks: Iterable[_HasDrinkInfo],
    tz: tzinfo,
    *,
    with_dates: bool = False,
    max_chars: int = 3000,
) -> str:
    """
    One line per drink, e.g. '21:30 🍺 33cl 4.7%'. With `with_dates` a '11.11.' heading is added
    whenever the date changes. Telegram messages are limited to 4096 characters, so a very long
    history is cut at `max_chars` (the drinks listed first are kept).
    """
    lines: list[str] = []
    day: str | None = None
    for drink in drinks:
        dt = datetime.fromtimestamp(drink.created, tz)
        if with_dates:
            short_date = f"{dt.day}.{dt.month}."
            if short_date != day:
                day = short_date
                lines.append(short_date)
        lines.append(f"{dt:%H:%M} {esc(drink.description or '')}")
    text = "\n".join(lines)
    if len(text) > max_chars:
        text = text[:max_chars].rsplit("\n", 1)[0] + "\n…"
    return text


def chunk_text(parts: Sequence[str], separator: str = "\n\n", limit: int = 4000) -> list[str]:
    """Join `parts` into as few messages as possible, keeping every message below `limit`."""
    messages: list[str] = []
    current = ""
    for part in parts:
        candidate = part if not current else current + separator + part
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            messages.append(current)
        # a single part that is too long is split hard
        while len(part) > limit:
            messages.append(part[:limit])
            part = part[limit:]
        current = part
    if current:
        messages.append(current)
    return messages
