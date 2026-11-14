"""Strict parsing of user input. Everything that comes from a chat is untrusted."""

from __future__ import annotations

import re

_INT_RE = re.compile(r"[0-9]{1,6}")
# ASCII digits (\d would also match e.g. Arabic-Indic and full-width digits, which int() accepts)
# with an optional decimal part, '.' or ',' as the separator. Deliberately does not accept
# what float() would (nan, inf, 1e9, signs, underscores, unicode digits...).
_FLOAT_RE = re.compile(r"(?:[0-9]{1,9}(?:[.,][0-9]{0,9})?|[.,][0-9]{1,9})")
_LEADING_INT_RE = re.compile(r"[0-9]{1,6}")

MAX_TEXT_LENGTH = 1000  # longer messages are not valid input for anything


def parse_int(text: str | None) -> int | None:
    if text is None:
        return None
    text = text.strip()
    return int(text) if _INT_RE.fullmatch(text) else None


def parse_float(text: str | None) -> float | None:
    if text is None:
        return None
    text = text.strip()
    if not _FLOAT_RE.fullmatch(text):
        return None
    return float(text.replace(",", "."))


def parse_leading_int(text: str | None) -> int | None:
    """Like JavaScript's parseInt: '7d' -> 7."""
    if text is None:
        return None
    match = _LEADING_INT_RE.match(text.strip())
    return int(match.group()) if match else None


def strip_suffix(word: str, suffix: str) -> str:
    """'33cl' -> '33'"""
    return word.removesuffix(suffix)


def in_range(value: float | int | None, low: float, high: float) -> bool:
    return value is not None and low <= value <= high
