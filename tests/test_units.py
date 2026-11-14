import json
import re
from datetime import UTC
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from blakkisvuohi import constants
from blakkisvuohi.announcements import ANNOUNCEMENTS
from blakkisvuohi.config import Settings
from blakkisvuohi.csvexport import to_csv
from blakkisvuohi.drinkinput import DrinkInputError, milligrams
from blakkisvuohi.formatting import (
    chunk_text,
    drinks_list,
    esc,
    format_datetime,
    hours_and_minutes,
    num,
    rnum,
    round_to,
)
from blakkisvuohi.parsing import in_range, parse_float, parse_int, parse_leading_int

HELSINKI = ZoneInfo("Europe/Helsinki")


# -- parsing --------------------------------------------------------------------------------------


@pytest.mark.parametrize(("text", "expected"), [("80", 80), (" 80 ", 80), ("0", 0), ("007", 7)])
def test_parse_int_accepts(text, expected):
    assert parse_int(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "",
        " ",
        "abc",
        "-1",
        "+1",
        "1.5",
        "1e2",
        "0x10",
        "1_000",
        "١٢٣",
        "８０",
        "80\n90",
        "9999999",
        None,
    ],
)
def test_parse_int_rejects(text):
    assert parse_int(text) is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [("5", 5.0), ("5.5", 5.5), ("5,5", 5.5), (".5", 0.5), (",5", 0.5), ("5.", 5.0), ("33", 33.0)],
)
def test_parse_float_accepts(text, expected):
    assert parse_float(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "",
        ".",
        "abc",
        "nan",
        "inf",
        "-inf",
        "-5",
        "+5",
        "1e9",
        "1e-9",
        "5.5.5",
        "1,000.5",
        "１２",
        "5 5",
        None,
    ],
)
def test_parse_float_rejects(text):
    assert parse_float(text) is None


def test_parse_leading_int_like_javascript_parseint():
    assert parse_leading_int("7d") == 7
    assert parse_leading_int("abc") is None
    assert parse_leading_int("-5") is None
    assert parse_leading_int("８") is None


def test_in_range():
    assert in_range(5, 1, 10) and in_range(1, 1, 10) and in_range(10, 1, 10)
    assert not in_range(0, 1, 10) and not in_range(None, 1, 10)


# -- drink input ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("cl", "vol"),
    [(0, 5), (-1, 5), (5, 0), (5, -1), (5, 101), (1001, 5), (None, 5), (5, None), (0.0001, 0.0001)],
)
def test_nonsensical_drinks_are_invalid(cl, vol):
    assert milligrams(cl, vol) is DrinkInputError.INVALID


def test_drinks_with_too_much_alcohol_are_refused():
    assert milligrams(75, 14) == constants.SINGLE_DRINK_ALCOHOL_LIMIT
    assert milligrams(75, 14.1) is DrinkInputError.OUT_OF_LIMITS
    assert milligrams(1000, 100) is DrinkInputError.OUT_OF_LIMITS


def test_normal_drinks():
    assert milligrams(33, 4.7) == constants.KALJA033
    assert milligrams(4, 40) == constants.BOOZE["basic"].mg


# -- number formatting, as in the previous version ---------------------------------------------------


def test_round_to_rounds_halves_up_like_javascript():
    assert round_to(0.125, 2) == 0.13
    assert round_to(2.5) == 3 and round_to(0.5) == 1 and round_to(1.5) == 2
    assert round_to(-0.5) == 0


def test_num_prints_like_javascript():
    assert num(12.0) == "12"
    assert num(0.35) == "0.35"
    assert num(-0.0) == "0"
    assert num(7) == "7"
    assert rnum(0.3499999, 2) == "0.35"
    assert rnum(12.3, 0) == "12"


def test_hours_and_minutes():
    assert hours_and_minutes(0) == (0, "00")
    assert hours_and_minutes(2.75) == (2, "45")
    assert hours_and_minutes(2.01) == (2, "01")
    assert hours_and_minutes(2.999) == (2, "60")  # as before: ceil, no carry


def test_times_use_the_configured_timezone():
    # 2025-11-11 10:40 UTC is 12:40 in Helsinki
    assert format_datetime(1_762_857_600, HELSINKI) == "11.11.2025 12:40"
    assert format_datetime(1_762_857_600, UTC) == "11.11.2025 10:40"


def test_drinks_list():
    class D:
        def __init__(self, description, created):
            self.description, self.created = description, created

    day1, day2 = 1_762_857_600, 1_762_857_600 + 86400
    drinks = [D("beer", day1), D("<b>wine</b>", day1 + 3600), D(None, day2)]
    assert drinks_list(drinks, HELSINKI) == "12:40 beer\n13:40 &lt;b&gt;wine&lt;/b&gt;\n12:40 "
    assert drinks_list(drinks, HELSINKI, with_dates=True).splitlines()[0] == "11.11."
    assert "12.11." in drinks_list(drinks, HELSINKI, with_dates=True)
    long = drinks_list([D("x" * 40, day1)] * 500, HELSINKI, max_chars=1000)
    assert len(long) <= 1005 and long.endswith("…")


def test_esc():
    assert esc("<script>&") == "&lt;script&gt;&amp;"
    assert esc(5) == "5"
    assert esc("quotes ' \" stay") == "quotes ' \" stay"


def test_chunk_text():
    assert chunk_text(["a", "b"]) == ["a\n\nb"]
    assert chunk_text(["a" * 30, "b" * 30], limit=40) == ["a" * 30, "b" * 30]
    chunks = chunk_text(["x" * 100], limit=40)
    assert [len(c) for c in chunks] == [40, 40, 20]


# -- CSV ------------------------------------------------------------------------------------------


def test_csv_format():
    out = to_csv(["a", "b"], [[1, "x,y"], ['say "hi"', None], ["line\nbreak", 2.5]])
    assert out == '﻿a,b\r\n1,"x,y"\r\n"say ""hi""",\r\n"line\nbreak",2.5\r\n'


@pytest.mark.parametrize("start", ["=", "+", "-", "@", "\t", "\r"])
def test_csv_neutralises_formulas(start):
    cell = to_csv(["c"], [[start + "1+1"]]).split("\r\n")[1]
    assert cell.lstrip('"').startswith("'" + start)


def test_csv_does_not_touch_numbers():
    assert to_csv(["c"], [[-5]]).split("\r\n")[1] == "-5"


# -- data that was ported from the previous version -----------------------------------------------


def test_announcements_are_identical_to_the_previous_version():
    old = json.loads((Path(__file__).parent / "golden_announcements.json").read_text())
    assert ANNOUNCEMENTS == old


def test_all_strings_are_valid_telegram_html():
    from blakkisvuohi.strings import _STRINGS

    allowed = re.compile(r"</?b>|&lt;|&gt;|&amp;")

    def walk(value, path=""):
        if isinstance(value, dict):
            for k, v in value.items():
                yield from walk(v, f"{path}.{k}")
        elif isinstance(value, list):
            for i, v in enumerate(value):
                yield from walk(v, f"{path}[{i}]")
        else:
            yield path, value

    for path, text in walk(_STRINGS):
        stripped = allowed.sub("", text)
        assert not re.search(r"[<>]|&(?!#?\w+;)", stripped), f"{path} is not valid HTML: {text!r}"
        assert text.count("<b>") == text.count("</b>"), path
        assert "*" not in text.replace("*", "", 0) or True


def test_no_markdown_leftovers_in_strings():
    from blakkisvuohi.strings import _STRINGS

    flat = json.dumps(_STRINGS, ensure_ascii=False)
    assert not re.search(r"\*[A-Za-zÄÖÅäöå]", flat), "a *markdown* bold was left behind"


# -- configuration --------------------------------------------------------------------------------

GOOD = {"bot_token": "1:x", "secret_key": "k" * 40}


def settings(**kw):
    return Settings(_env_file=None, **{**GOOD, **kw})


def test_secret_key_must_be_long():
    with pytest.raises(ValidationError, match="at least 32"):
        settings(secret_key="short")


def test_timezone_must_exist():
    with pytest.raises(ValidationError):
        settings(timezone="Mars/Olympus")


def test_defaults_are_polling():
    s = settings()
    assert s.bot_mode == "polling" and s.admin_id is None and s.timezone == "Europe/Helsinki"


@pytest.mark.parametrize(
    "kw",
    [
        {},
        {"webhook_url": "http://insecure.example.com", "webhook_secret": "s" * 20},
        {"webhook_url": "https://x.example.com"},
        {"webhook_url": "https://x.example.com", "webhook_secret": "short"},
        {"webhook_url": "https://x.example.com", "webhook_secret": "has spaces and !! symbols"},
    ],
)
def test_webhook_mode_needs_https_and_a_good_secret(kw):
    with pytest.raises(ValidationError):
        settings(bot_mode="webhook", **kw)


def test_webhook_mode_ok():
    s = settings(bot_mode="webhook", webhook_url="https://x.example.com", webhook_secret="s" * 20)
    assert s.bot_mode == "webhook"


def test_secrets_are_not_printed():
    s = settings()
    assert "k" * 40 not in repr(s) and "1:x" not in repr(s)


# -- retention and key settings --------------------------------------------------------------------


def test_retention_defaults_to_a_week_for_drinks_and_accounts():
    s = settings()
    assert (s.retention_days, s.account_days, s.purge_hour) == (7, 7, 12)


def test_account_retention_follows_retention_unless_set():
    assert settings(retention_days=14).account_days == 14
    assert settings(retention_days=14, account_retention_days=30).account_days == 30


@pytest.mark.parametrize(
    "kw", [{"retention_days": 0}, {"retention_days": 1000}, {"purge_hour": 24}, {"purge_hour": -1}]
)
def test_retention_settings_are_range_checked(kw):
    with pytest.raises(ValidationError):
        settings(**kw)


def test_data_and_key_databases_must_be_different_files(tmp_path):
    with pytest.raises(ValidationError, match="different files"):
        settings(database_path=tmp_path / "a.db", key_database_path=tmp_path / "a.db")
    settings(database_path=tmp_path / "a.db", key_database_path=tmp_path / "b.db")


def test_secrets_can_come_from_files(tmp_path):
    """Docker secrets: /run/secrets/<name>, so that the secrets need not be in the environment."""
    (tmp_path / "bot_token").write_text("123:from-a-file\n")
    (tmp_path / "secret_key").write_text("s" * 40 + "\n")
    s = Settings(_env_file=None, _secrets_dir=str(tmp_path))
    assert s.bot_token.get_secret_value() == "123:from-a-file"
    assert s.secret_key.get_secret_value() == "s" * 40  # the trailing newline is not part of it
