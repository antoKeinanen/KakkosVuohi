from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from .. import alcomath, constants
from ..security import DataKey
from . import codec
from .database import Database, Transaction
from .models import DrinkRow, DrinkSum, RetentionPolicy, User
from .users import AccountGone
from .vault import Vault

# How far back drinks are looked at when estimating the current EBAC (the retention period caps it)
EBAC_WINDOW_HOURS = 7 * 24

# A user may have this many drinks within the retention period. It bounds the size of the blob
# that is rewritten at every drink, and protects the database from being filled by one account.
MAX_DRINKS_PER_USER = 1000


@dataclass(frozen=True, slots=True)
class LateDrink:
    text: str
    mg: int


class TooManyDrinks(Exception):
    pass


async def bump_counters(tx: Transaction, drinks: int, milligrams: int) -> None:
    """Counters of everything ever recorded. They contain no personal data."""
    await tx.execute(
        "UPDATE meta SET value = CAST(value AS INTEGER) + ? WHERE key = 'drinks_total'", (drinks,)
    )
    await tx.execute(
        "UPDATE meta SET value = CAST(value AS INTEGER) + ? WHERE key = 'alcohol_total'",
        (milligrams,),
    )


class DrinkRepository:
    def __init__(
        self,
        db: Database,
        vault: Vault,
        clock: Callable[[], float] = time.time,
        policy: RetentionPolicy | None = None,
    ) -> None:
        self._db = db
        self._vault = vault
        self._clock = clock
        self._policy = policy or RetentionPolicy()

    def now(self) -> int:
        return int(self._clock())

    # -- plumbing -----------------------------------------------------------------------------

    async def _key(self, user: User) -> DataKey:
        key = await self._vault.get(user.user_id)
        if key is None:
            raise AccountGone
        return key

    async def _read(
        self, q: Database | Transaction, user_id: str, key: DataKey
    ) -> tuple[list[DrinkRow], int]:
        """The drinks within the retention period, oldest first, and how many are past it."""
        row = await q.fetchone("SELECT drinks FROM users WHERE user_id = ?", (user_id,))
        if row is None:
            raise AccountGone
        everything = codec.open_drinks(key, user_id, row["drinks"])
        cutoff = self._policy.drink_cutoff(self._clock())
        live = [d for d in everything if d.created >= cutoff]
        live.sort(key=lambda d: d.created)  # stable: drinks of the same second keep their order
        return live, len(everything) - len(live)

    @staticmethod
    async def _write(tx: Transaction, user_id: str, key: DataKey, drinks: list[DrinkRow]) -> None:
        await tx.execute(
            "UPDATE users SET drinks = ? WHERE user_id = ?",
            (codec.seal_drinks(key, user_id, drinks), user_id),
        )

    async def _all(self, user: User) -> list[DrinkRow]:
        drinks, _ = await self._read(self._db, user.user_id, await self._key(user))
        return drinks

    def _since(self, hours: float) -> float:
        return self._clock() - hours * constants.HOUR

    # -- writing ------------------------------------------------------------------------------

    async def add(self, user: User, milligrams: int, description: str) -> None:
        await self._append(user, [DrinkRow(milligrams, description, self.now())])

    async def add_late(self, user: User, drinks: Sequence[LateDrink], hours: float) -> None:
        """Spread the drinks evenly over the last `hours` hours, the first one being the oldest."""
        now = self._clock()
        await self._append(
            user,
            [
                DrinkRow(
                    d.mg,
                    d.text,
                    int(now - (hours - (hours / max(len(drinks) - 1, 1)) * i) * constants.HOUR),
                )
                for i, d in enumerate(drinks)
            ],
        )

    async def _append(self, user: User, new: list[DrinkRow]) -> None:
        if not new:
            return
        key = await self._key(user)
        async with self._db.transaction() as tx:
            drinks, _ = await self._read(tx, user.user_id, key)
            if len(drinks) + len(new) > MAX_DRINKS_PER_USER:
                raise TooManyDrinks
            await self._write(tx, user.user_id, key, drinks + new)
            await bump_counters(tx, len(new), sum(d.alcohol for d in new))

    async def undo_last(self, user: User) -> None:
        key = await self._key(user)
        async with self._db.transaction() as tx:
            drinks, _ = await self._read(tx, user.user_id, key)
            if not drinks:
                return
            last = drinks.pop()  # the latest one: the list is ordered by time
            await self._write(tx, user.user_id, key, drinks)
            await bump_counters(tx, -1, -last.alcohol)

    async def trim(self, user_id: str, key: DataKey) -> int:
        """Physically delete the drinks that are past the retention period. Returns how many."""
        async with self._db.transaction() as tx:
            drinks, expired = await self._read(tx, user_id, key)
            if expired:
                await self._write(tx, user_id, key, drinks)
            return expired

    # -- reading ------------------------------------------------------------------------------

    async def since(self, user: User, hours: float) -> list[DrinkRow]:
        """Drinks of the last `hours` hours, oldest first."""
        cutoff = self._since(hours)
        return [d for d in await self._all(user) if d.created > cutoff]

    async def last_hours(self, user: User, hours: float) -> list[DrinkRow]:
        """Drinks of the last `hours` hours, newest first."""
        return (await self.since(user, hours))[::-1]

    async def sum_for_hours(self, user: User, hours: float) -> DrinkSum:
        drinks = await self.since(user, hours)
        return DrinkSum(
            sum=sum(d.alcohol for d in drinks),
            first_drink=min((d.created for d in drinks), default=None),
        )

    async def last(self, user: User) -> DrinkRow | None:
        drinks = await self._all(user)
        return drinks[-1] if drinks else None

    async def last_unique(self, user: User, n: int, exclude_prefix: str = "") -> list[DrinkRow]:
        """The latest `n` differently named drinks, newest first. For the quick pick buttons."""
        seen: set[str | None] = set()
        picked: list[DrinkRow] = []
        excluded = exclude_prefix.casefold()
        for drink in reversed(await self._all(user)):
            if excluded and (drink.description or "").casefold().startswith(excluded):
                continue
            if drink.description in seen:
                continue
            seen.add(drink.description)
            picked.append(drink)
            if len(picked) == n:
                break
        return picked

    async def ebac(self, user: User) -> alcomath.EBAC:
        cutoff = self._since(EBAC_WINDOW_HOURS)
        drinks = [d for d in await self._all(user) if d.created > cutoff]
        return alcomath.calculate_ebac(user, drinks, self._clock())

    async def ebac_with_recent(
        self, user: User, hours: float
    ) -> tuple[alcomath.EBAC, list[DrinkRow]]:
        """EBAC together with the drinks of the last `hours` hours (newest first)."""
        return await self.ebac(user), await self.last_hours(user, hours)

    async def chart_drinks(self, user: User) -> list[DrinkRow]:
        return await self.since(user, 48)
