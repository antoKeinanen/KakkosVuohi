"""
Alcohol related math wizardry.

Variation of the Widmark equation, from the original article "The Estimation of Blood Alcohol
Concentration", DOI: 10.1385/Forensic Sci. Med. Pathol.:3:1:33

Most BAC calculations are based on the Widmark formula,

    C = A/(rW) - (βt)

where C is the blood alcohol concentration; A is the mass of alcohol consumed; r is the Widmark
factor; W is body weight; t is elapsed time since the start of drinking; and β is the elimination
rate.

In addition, alcohol absorption is taken into account:

    BAC = (A[ingested]*(1 - e^(-t*ln(2)/t[1_2])) - (βt[n]))/(r*W)

where t[1_2] is the time constant for absorption half life (0.1066 for empty stomach).

The total observed BAC is the sum of the BACs of each individual drink, minus the elimination.

Ethanol mass of a serving = volume * (alcohol by volume * 789.24 g/l)
e.g. 20cl of 40% vodka: 0.20l * 0.4 * 789.24g/l = 63.1392g

NOTE: all of the constants below (including feeding the height in *centimetres* to the Widmark
factor, and MAGIC_NUMBER) are an empirical calibration inherited from the previous version of the
bot. Changing any of them changes every number the bot prints.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, tzinfo
from typing import Protocol

from . import constants

# found by trial and error when comparing to multiple measurements
MAGIC_NUMBER = 6.9
ABSORPTION_HALF_LIFE = 0.1066  # hours


class UserLike(Protocol):
    weight: int
    height: int
    gender: str


class DrinkLike(Protocol):
    alcohol: int  # milligrams of pure alcohol
    created: float  # unix timestamp, seconds


@dataclass(frozen=True, slots=True)
class EBAC:
    permilles: float
    permilles_30min: float
    grams: float
    burn_hours: float


@dataclass(frozen=True, slots=True)
class HourlyEBAC:
    permilles: float
    hour: int
    time: float


def widmark_factor(user: UserLike) -> float:
    """
    Seidl et al. gathered height, weight, blood water content and TBW data for 256 women and
    273 men and used the data to fine tune the Widmark equation:

        r(female) = 0.31223 - 0.006446W + 0.4466H
        r(male)   = 0.31608 - 0.004821W + 0.4632H
    """
    h, w = user.height, user.weight
    if user.gender == constants.GENDER_MALE:
        return 0.31608 - 0.004821 * w + 0.4632 * h
    return 0.31223 - 0.006446 * w + 0.4466 * h


def metabolism_rate(user: UserLike | None = None) -> float:
    # TODO: maybe mean+-0.01 based on drinking habits
    return constants.METABOLISM_RATE


def absorbed_alcohol_concentration(
    user: UserLike, milligrams: float, drinking_period: float
) -> float:
    """Permilles of the drink that have been absorbed `drinking_period` hours after drinking it."""
    grams = milligrams / 1000
    a = grams / MAGIC_NUMBER
    r = widmark_factor(user)
    eaac = (
        (a * (1 - math.exp(-drinking_period * math.log(2) / ABSORPTION_HALF_LIFE)))
        / (r * user.weight)
        * 1000
    )
    return eaac if eaac > 0 else 0.0


def estimate_unburned_alcohol(user: UserLike, ebac: float) -> float:
    """Grams of alcohol that corresponds to the given permilles."""
    r = widmark_factor(user)
    t = 0.5
    a = (
        ((ebac / 1000) * (r * user.weight))
        / (1 - math.exp(-t * math.log(2) / ABSORPTION_HALF_LIFE))
        * MAGIC_NUMBER
    )
    return a if a > 0 else 0.0


def calculate_ebac(user: UserLike, drinks: Sequence[DrinkLike], now: float) -> EBAC:
    """`drinks` must be ordered from the oldest to the newest."""
    if not drinks:
        return EBAC(0.0, 0.0, 0.0, 0.0)

    in_30_mins = now + constants.HOUR * 0.5
    mr = metabolism_rate(user)

    absorbed = 0.0
    absorbed_in_30 = 0.0
    start_time = drinks[0].created
    for drink in drinks:
        burn_time = (drink.created - start_time) / constants.HOUR
        if absorbed - mr * burn_time <= 0:
            # everything earlier has burned away, start counting again from this drink
            absorbed = 0.0
            absorbed_in_30 = 0.0
            start_time = drink.created
        absorbed += absorbed_alcohol_concentration(
            user, drink.alcohol, (now - drink.created) / constants.HOUR
        )
        absorbed_in_30 += absorbed_alcohol_concentration(
            user, drink.alcohol, (in_30_mins - drink.created) / constants.HOUR
        )

    permilles = max(absorbed - mr * max((now - start_time) / constants.HOUR, 0), 0)
    permilles_30min = max(
        absorbed_in_30 - mr * max((in_30_mins - start_time) / constants.HOUR, 0), 0
    )
    burn_hours = permilles_30min / mr
    if burn_hours > 0:
        burn_hours += 0.5

    return EBAC(
        permilles=permilles,
        permilles_30min=permilles_30min,
        grams=estimate_unburned_alcohol(user, permilles),
        burn_hours=burn_hours,
    )


def calculate_ebac_by_hour(
    user: UserLike,
    drinks: Sequence[DrinkLike],
    last_n_hours: int,
    predict_n_hours: int,
    now: float,
    tz: tzinfo,
) -> list[HourlyEBAC]:
    start_time = now - constants.HOUR * last_n_hours - (now % constants.HOUR)  # floor to hours
    mr = metabolism_rate(user)

    result: list[HourlyEBAC] = []
    for i in range(last_n_hours + predict_n_hours + 1):
        time = start_time + constants.HOUR * i
        absorbed = 0.0
        absorption_start = drinks[0].created
        for drink in drinks:
            burn_time = (drink.created - absorption_start) / constants.HOUR
            if time - drink.created > 0:
                if absorbed - mr * burn_time <= 0:
                    absorbed = 0.0
                    absorption_start = drink.created
                absorbed += absorbed_alcohol_concentration(
                    user, drink.alcohol, (time - drink.created) / constants.HOUR
                )
        permilles = max(absorbed - mr * max((time - absorption_start) / constants.HOUR, 0), 0)
        result.append(HourlyEBAC(permilles, datetime.fromtimestamp(time, tz).hour, time))
    return result


def to_standard_drinks(alcohol_grams: float) -> float:
    return alcohol_grams / constants.STANDARD_DRINK_GRAMS


def is_alcohol_amount_out_of_limits(milligrams: float) -> bool:
    return milligrams > constants.SINGLE_DRINK_ALCOHOL_LIMIT
