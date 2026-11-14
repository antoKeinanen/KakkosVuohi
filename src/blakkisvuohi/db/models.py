from __future__ import annotations

from dataclasses import dataclass, field

from ..constants import HOUR
from ..security import DataKey

DAY = 24 * HOUR


def day_number(timestamp: float) -> int:
    """Whole (UTC) days since the epoch. The only precision 'last used' is ever stored with."""
    return int(timestamp // DAY)


@dataclass(frozen=True, slots=True)
class RetentionPolicy:
    """How long things are kept. The daily purge deletes what is older; reads ignore it already."""

    drink_days: int = 7
    account_days: int = 7

    def drink_cutoff(self, now: float) -> float:
        return now - self.drink_days * DAY

    def account_cutoff_day(self, now: float) -> int:
        """Accounts whose last use was on an earlier day than this are deleted."""
        return day_number(now) - self.account_days


@dataclass(frozen=True, slots=True)
class User:
    user_id: str  # pseudonymous id (HMAC of the Telegram id), NOT the Telegram id
    nick: str
    weight: int
    gender: str  # 'mies' | 'nainen'
    height: int
    read_terms: bool
    read_announcements: int
    last_active_day: int  # day_number() of the latest use of the bot


@dataclass(frozen=True, slots=True)
class DrinkRow:
    alcohol: int  # milligrams
    description: str | None
    created: int  # unix time


@dataclass(frozen=True, slots=True)
class Account:
    """A decrypted account: the profile and the drinks that are within the retention period."""

    user: User
    key: DataKey = field(repr=False)
    drinks: list[DrinkRow]
    expired_drinks: int  # drinks that are past the retention period, waiting for the purge


@dataclass(slots=True)
class GroupMember:
    """A member of a group together with their recent drinks, oldest first."""

    user_id: str
    nick: str
    weight: int
    gender: str
    height: int
    drinks: list[DrinkRow] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class UserCount:
    nick: str
    count: int


@dataclass(frozen=True, slots=True)
class UserSum:
    nick: str
    sum: int  # milligrams


@dataclass(frozen=True, slots=True)
class DrinkSum:
    sum: int  # milligrams
    first_drink: int | None  # unix time of the earliest drink in the range


@dataclass(frozen=True, slots=True)
class GlobalStats:
    users: int
    active_users_1d: int
    active_users_7d: int
    groups: int
    drinks_now: int  # drinks currently stored (the retention period)
    drinks_total: int  # drinks ever recorded
    top10: list[UserCount]


@dataclass(frozen=True, slots=True)
class GroupStats:
    top10: list[UserCount]
    group_sum: DrinkSum
    global_drinks: int  # drinks ever recorded by everybody


@dataclass(frozen=True, slots=True)
class GroupAlcoholStats:
    top10: list[UserSum]
    group_sum: DrinkSum
    global_alcohol: int  # milligrams ever recorded by everybody


@dataclass(frozen=True, slots=True)
class Table:
    columns: list[str]
    rows: list[list[object]]


@dataclass(frozen=True, slots=True)
class UserData:
    user: Table
    drinks: Table
    groups: Table

    def is_empty(self) -> bool:
        return not (self.user.rows or self.drinks.rows or self.groups.rows)


@dataclass(slots=True)
class PurgeReport:
    accounts_scanned: int = 0
    accounts_deleted: int = 0
    drinks_deleted: int = 0
    orphans_removed: int = 0
    seconds: float = 0.0
