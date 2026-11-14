"""RFC 4180 CSV export for /data."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

_FORMULA_START = re.compile(r"^[=+\-@\t\r]")


def _cell(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    # Stop spreadsheet programs from running user-entered text as a formula
    if isinstance(value, str) and _FORMULA_START.match(text):
        text = "'" + text
    if re.search(r'[",\r\n]', text):
        text = '"' + text.replace('"', '""') + '"'
    return text


def to_csv(columns: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    """
    The leading byte order mark makes Excel read the file as UTF-8, so that ä and ö stay intact.
    """
    lines = [list(columns), *rows]
    return "﻿" + "".join(",".join(_cell(c) for c in line) + "\r\n" for line in lines)
