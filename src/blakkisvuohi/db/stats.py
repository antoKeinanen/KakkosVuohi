from __future__ import annotations

import time
from collections.abc import Callable

from .. import constants
from ..security import Crypto
from .database import Database
from .groups import GroupRepository
from .models import (
    DrinkSum,
    GlobalStats,
    GroupAlcoholStats,
    GroupStats,
    UserCount,
    UserSum,
    day_number,
)
from .users import UserRepository


class StatsRepository:
    def __init__(
        self,
        db: Database,
        crypto: Crypto,
        users: UserRepository,
        groups: GroupRepository,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._db = db
        self._crypto = crypto
        self._users = users
        self._groups = groups
        self._clock = clock

    async def _counter(self, key: str) -> int:
        row = await self._db.fetchone("SELECT value FROM meta WHERE key = ?", (key,))
        return int(row["value"]) if row else 0

    async def global_stats(self) -> GlobalStats:
        today = day_number(self._clock())
        users = active_1d = active_7d = drinks = 0
        counts: list[UserCount] = []
        async for account in self._users.scan():
            users += 1
            idle_days = today - account.user.last_active_day
            active_1d += idle_days <= 1
            active_7d += idle_days <= 7
            drinks += len(account.drinks)
            counts.append(UserCount(account.user.nick, len(account.drinks)))
        groups = await self._db.fetchone("SELECT COUNT(DISTINCT group_id) FROM users_in_groups")
        counts.sort(key=lambda c: c.count, reverse=True)
        return GlobalStats(
            users=users,
            active_users_1d=active_1d,
            active_users_7d=active_7d,
            groups=groups[0] if groups else 0,
            drinks_now=drinks,
            drinks_total=await self._counter("drinks_total"),
            top10=[c for c in counts if c.count][:10],
        )

    async def _members(self, chat_id: int, hours: float):  # noqa: ANN202
        return list((await self._groups.members_with_drinks(chat_id, hours)).values())

    @staticmethod
    def _group_sum(members, since: float) -> DrinkSum:  # noqa: ANN001
        drinks = [d for m in members for d in m.drinks if d.created >= since]
        return DrinkSum(
            sum=sum(d.alcohol for d in drinks),
            first_drink=min((d.created for d in drinks), default=None),
        )

    async def group_stats(self, chat_id: int, hours: float) -> GroupStats:
        members = await self._members(chat_id, hours)
        since = self._clock() - hours * constants.HOUR
        ranked = sorted(
            (UserCount(m.nick, sum(d.created >= since for d in m.drinks)) for m in members),
            key=lambda c: (-c.count, c.nick),
        )
        return GroupStats(
            top10=ranked[:10],
            group_sum=self._group_sum(members, since),
            global_drinks=await self._counter("drinks_total"),
        )

    async def group_alcohol_stats(self, chat_id: int, hours: float) -> GroupAlcoholStats:
        members = await self._members(chat_id, hours)
        since = self._clock() - hours * constants.HOUR
        ranked = sorted(
            (
                UserSum(m.nick, sum(d.alcohol for d in m.drinks if d.created >= since))
                for m in members
            ),
            key=lambda u: (-u.sum, u.nick),
        )
        return GroupAlcoholStats(
            top10=ranked[:10],
            group_sum=self._group_sum(members, since),
            global_alcohol=await self._counter("alcohol_total"),
        )
