"""
The encrypted layout of a user's data. This is the only module that knows it.

Everything is sealed with the user's own key and bound (as AAD) to the user's pseudonymous id and
to what it is, so a blob cannot be moved to another row or used as another kind of blob.
"""

from __future__ import annotations

from .. import constants
from ..security import DataKey
from .models import DrinkRow, User

# Ciphertexts are padded to a multiple of this, so that their length reveals little. A profile
# fits in one block; ~40 drinks fit in one block of the drinks.
PROFILE_PAD = 256
DRINKS_PAD = 2048


def validate_profile(user: User) -> None:
    """The database cannot check encrypted values, so they are checked before they are written."""
    low, high = constants.WEIGHT_RANGE
    if not low <= user.weight <= high:
        raise ValueError("weight out of range")
    low, high = constants.HEIGHT_RANGE
    if not low <= user.height <= high:
        raise ValueError("height out of range")
    if user.gender not in (constants.GENDER_MALE, constants.GENDER_FEMALE):
        raise ValueError("invalid gender")
    if not user.nick or len(user.nick) > 256:
        raise ValueError("invalid nickname")
    if user.read_announcements < 0:
        raise ValueError("invalid announcement count")


def seal_profile(key: DataKey, user: User) -> str:
    validate_profile(user)
    return key.seal(
        {
            "nick": user.nick,
            "weight": user.weight,
            "height": user.height,
            "gender": user.gender,
            "terms": user.read_terms,
            "announcements": user.read_announcements,
            "active": user.last_active_day,
        },
        aad=f"{user.user_id}:profile",
        pad_to=PROFILE_PAD,
    )


def open_profile(key: DataKey, user_id: str, token: str) -> User:
    p = key.open(token, aad=f"{user_id}:profile")
    return User(
        user_id=user_id,
        nick=p["nick"],
        weight=p["weight"],
        gender=p["gender"],
        height=p["height"],
        read_terms=bool(p["terms"]),
        read_announcements=p["announcements"],
        last_active_day=p["active"],
    )


def seal_drinks(key: DataKey, user_id: str, drinks: list[DrinkRow]) -> str:
    return key.seal(
        [[d.created, d.alcohol, d.description] for d in drinks],
        aad=f"{user_id}:drinks",
        pad_to=DRINKS_PAD,
    )


def open_drinks(key: DataKey, user_id: str, token: str) -> list[DrinkRow]:
    return [
        DrinkRow(alcohol=alcohol, description=description, created=created)
        for created, alcohol, description in key.open(token, aad=f"{user_id}:drinks")
    ]
