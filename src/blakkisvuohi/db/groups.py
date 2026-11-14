from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from .. import alcomath, constants
from ..security import Crypto
from .database import Database
from .models import GroupMember, User
from .users import UserRepository

# Only the last two days of drinks are used for the group listings and charts
GROUP_WINDOW_HOURS = 48


@dataclass(frozen=True, slots=True)
class ListingEntry:
    nick: str
    value: float  # permilles, or standard drinks of alcohol in the blood
    standard_drinks_12h: float
    standard_drinks_24h: float


class GroupRepository:
    def __init__(
        self,
        db: Database,
        crypto: Crypto,
        users: UserRepository,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._db = db
        self._crypto = crypto
        self._users = users
        self._clock = clock

    async def join(self, user: User, chat_id: int) -> None:
        await self._db.execute(
            "INSERT OR IGNORE INTO users_in_groups (user_id, group_id) VALUES (?, ?)",
            (user.user_id, self._crypto.group_id(chat_id)),
        )

    async def leave(self, user: User, chat_id: int) -> None:
        await self._db.execute(
            "DELETE FROM users_in_groups WHERE user_id = ? AND group_id = ?",
            (user.user_id, self._crypto.group_id(chat_id)),
        )

    async def members_with_drinks(
        self, chat_id: int, hours: float = GROUP_WINDOW_HOURS
    ) -> dict[str, GroupMember]:
        """Members of the group that have drunk in the last `hours` hours, with those drinks."""
        rows = await self._db.fetchall(
            "SELECT user_id FROM users_in_groups WHERE group_id = ?",
            (self._crypto.group_id(chat_id),),
        )
        since = self._clock() - hours * constants.HOUR
        members: dict[str, GroupMember] = {}
        for account in await self._users.accounts([r["user_id"] for r in rows]):
            drinks = [d for d in account.drinks if d.created >= since]
            if drinks:
                user = account.user
                members[user.user_id] = GroupMember(
                    user.user_id, user.nick, user.weight, user.gender, user.height, drinks
                )
        # the oldest drinker first, as when this was one SQL query ordered by time
        return dict(sorted(members.items(), key=lambda kv: kv[1].drinks[0].created))

    def _standard_drinks_since(self, member: GroupMember, hours: float) -> float:
        since = self._clock() - hours * constants.HOUR
        milligrams = sum(d.alcohol for d in member.drinks if d.created >= since)
        return milligrams / (constants.STANDARD_DRINK_GRAMS * 1000)

    async def _listing(self, chat_id: int, *, grams: bool) -> list[ListingEntry]:
        now = self._clock()
        entries = []
        for member in (await self.members_with_drinks(chat_id)).values():
            ebac = alcomath.calculate_ebac(member, member.drinks, now)
            value = ebac.grams if grams else ebac.permilles
            if value > 0:
                entries.append(
                    ListingEntry(
                        nick=member.nick,
                        value=value / constants.STANDARD_DRINK_GRAMS if grams else value,
                        standard_drinks_12h=self._standard_drinks_since(member, 12),
                        standard_drinks_24h=self._standard_drinks_since(member, 24),
                    )
                )
        return sorted(entries, key=lambda e: e.value, reverse=True)

    async def permilles_listing(self, chat_id: int) -> list[ListingEntry]:
        return await self._listing(chat_id, grams=False)

    async def standard_drinks_listing(self, chat_id: int) -> list[ListingEntry]:
        return await self._listing(chat_id, grams=True)
