"""Validation of drinks that users type in by hand (volume in centilitres and alcohol percent)."""

from __future__ import annotations

from enum import Enum

from . import alcomath, constants

MAX_CENTILITRES = 1000
MAX_LATE_DRINKS = 50  # per /jalkikellotus session


class DrinkInputError(Enum):
    INVALID = "invalid"  # not a sensible volume or percentage
    OUT_OF_LIMITS = "out_of_limits"  # more alcohol than a single drink can contain


def milligrams(centilitres: float | None, vol_percent: float | None) -> int | DrinkInputError:
    """The milligrams of pure alcohol in the drink, or what is wrong with the input."""
    if (
        centilitres is None
        or vol_percent is None
        or not 0 < centilitres <= MAX_CENTILITRES
        or not 0 < vol_percent <= 100
    ):
        return DrinkInputError.INVALID
    mg = constants.calc_alcohol_milligrams(vol_percent / 100.0, centilitres / 100.0)
    if mg <= 0:
        return DrinkInputError.INVALID
    if alcomath.is_alcohol_amount_out_of_limits(mg):
        return DrinkInputError.OUT_OF_LIMITS
    return mg
