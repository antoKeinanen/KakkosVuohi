"""Commonly used constants."""

from __future__ import annotations

import math
from dataclasses import dataclass

ETHANOL_GRAMS_PER_LITRE = 789.24
HOUR = 3600  # seconds
METABOLISM_RATE = 0.17  # permilles per hour, mean is usually between 0.15-0.20
STANDARD_DRINK_GRAMS = 12.0

GENDER_MALE = "mies"
GENDER_FEMALE = "nainen"

WEIGHT_RANGE = (20, 250)  # kg
HEIGHT_RANGE = (120, 240)  # cm
# Weight and height are stored this coarsely (data minimisation): it costs about 3 % of accuracy
# in the worst case and makes the stored values far less identifying. Set to 1 to store exact values.
PROFILE_STEP = 5


def round_half_up(value: float) -> int:
    """Rounding the way JavaScript's Math.round does it (the previous version's behaviour)."""
    return math.floor(value + 0.5)


def coarsen(value: int, low: int, high: int, step: int = PROFILE_STEP) -> int:
    """Round to the nearest `step`, staying within [low, high]."""
    return min(max(round_half_up(value / step) * step, low), high)


def calc_alcohol_milligrams(vol_fraction: float, litres: float) -> int:
    return round_half_up(vol_fraction * ETHANOL_GRAMS_PER_LITRE * litres * 1000)


KALJA033 = calc_alcohol_milligrams(0.047, 0.33)
KALJA05 = calc_alcohol_milligrams(0.047, 0.5)
# 14% sparkling wine bottle: no single drink may contain more alcohol than this
SINGLE_DRINK_ALCOHOL_LIMIT = calc_alcohol_milligrams(0.14, 0.75)

BEER = "🍺"
WINE = "🍷"


@dataclass(frozen=True, slots=True)
class Drink:
    name: str
    mg: int


# Drinks of the keyboard based /juoma command
MILDS: dict[str, Drink] = {
    "beercan": Drink(f"{BEER} 33cl 4.7%", calc_alcohol_milligrams(0.047, 0.33)),
    "beer04": Drink(f"{BEER} 40cl 4.7%", calc_alcohol_milligrams(0.047, 0.4)),
    "beer4": Drink(f"{BEER} 33cl 5.5%", calc_alcohol_milligrams(0.055, 0.33)),
    "beer05": Drink(f"{BEER} 50cl 4.7%", calc_alcohol_milligrams(0.047, 0.5)),
    "beerpint": Drink(f"{BEER} 56.8cl 4.7%", calc_alcohol_milligrams(0.047, 0.568)),
    "lonkero": Drink("Lonkero 33cl 5.3%", calc_alcohol_milligrams(0.053, 0.33)),
    "wine12": Drink(f"{WINE} 12cl 12%", calc_alcohol_milligrams(0.12, 0.12)),
    "wine16": Drink(f"{WINE} 16cl 12%", calc_alcohol_milligrams(0.12, 0.16)),
}

BOOZE: dict[str, Drink] = {
    "mild": Drink("20% 4cl", calc_alcohol_milligrams(0.2, 0.04)),
    "medium": Drink("32% 4cl", calc_alcohol_milligrams(0.32, 0.04)),
    "basic": Drink("40% 4cl", calc_alcohol_milligrams(0.4, 0.04)),
}
