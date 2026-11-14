from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
import time
from collections.abc import AsyncIterator, Callable, Sequence
from datetime import UTC, datetime
from typing import Any

from .. import constants
from ..announcements import ANNOUNCEMENTS
from ..security import Crypto, DecryptionError
from . import codec
from .database import Database
from .models import (
    Account,
    RetentionPolicy,
    Table,
    User,
    UserData,
    day_number,
)
from .vault import Vault

log = logging.getLogger("blakkis.db")
_CHUNK = 500


class AccountGone(Exception):
    """The account does not exist (any more): it was deleted, possibly a moment ago."""


class UserRepository:
    def __init__(
        self,
        db: Database,
        vault: Vault,
        crypto: Crypto,
        clock: Callable[[], float] = time.time,
        policy: RetentionPolicy | None = None,
    ) -> None:
        self._db = db
        self._vault = vault
        self._crypto = crypto
        self._clock = clock
        self._policy = policy or RetentionPolicy()

    # -- reading ------------------------------------------------------------------------------

    async def find(self, telegram_id: int) -> User | None:
        user_id = self._crypto.user_id(telegram_id)
        row = await self._db.fetchone("SELECT profile FROM users WHERE user_id = ?", (user_id,))
        if row is None:
            return None
        key = await self._vault.get(user_id)
        if key is None:  # the key was destroyed: the account is as good as deleted
            return None
        return codec.open_profile(key, user_id, row["profile"])

    async def accounts(self, user_ids: Sequence[str]) -> list[Account]:
        """
        Decrypted accounts of the given users, in no particular order. Accounts that cannot be read
        (no key, or damaged) are left out. Drinks past the retention period are not included.
        """
        keys = await self._vault.get_many(user_ids)
        cutoff = self._policy.drink_cutoff(self._clock())
        accounts: list[Account] = []
        for i in range(0, len(user_ids), _CHUNK):
            chunk = list(user_ids[i : i + _CHUNK])
            rows = await self._db.fetchall(
                "SELECT user_id, profile, drinks FROM users "
                "WHERE user_id IN (SELECT value FROM json_each(?))",
                (json.dumps(chunk),),
            )
            for row in rows:
                key = keys.get(row["user_id"])
                if key is None:
                    continue
                try:
                    user = codec.open_profile(key, row["user_id"], row["profile"])
                    everything = codec.open_drinks(key, row["user_id"], row["drinks"])
                except DecryptionError:
                    log.error("An account cannot be decrypted, skipping it")
                    continue
                live = [d for d in everything if d.created >= cutoff]
                accounts.append(Account(user, key, live, len(everything) - len(live)))
        return accounts

    async def scan(self, batch: int = 200) -> AsyncIterator[Account]:
        """Every readable account, a batch at a time, so that the bot stays responsive."""
        ids = [r[0] for r in await self._db.fetchall("SELECT user_id FROM users")]
        for i in range(0, len(ids), batch):
            for account in await self.accounts(ids[i : i + batch]):
                yield account
            await asyncio.sleep(0)

    # -- writing ------------------------------------------------------------------------------

    async def create_or_update(
        self, telegram_id: int, nick: str, weight: int, gender: str, height: int
    ) -> tuple[User, bool]:
        """Sign up, or update the details of an existing user. Accepting the terms is implied."""
        user_id = self._crypto.user_id(telegram_id)
        weight = constants.coarsen(weight, *constants.WEIGHT_RANGE)
        height = constants.coarsen(height, *constants.HEIGHT_RANGE)
        existing = await self.find(telegram_id)
        key = await self._vault.create(user_id)
        today = day_number(self._clock())

        async with self._db.transaction() as tx:
            if existing is not None:
                user = dataclasses.replace(
                    existing,
                    nick=nick,
                    weight=weight,
                    gender=gender,
                    height=height,
                    read_terms=True,
                    last_active_day=today,
                )
                await tx.execute(
                    "UPDATE users SET profile = ? WHERE user_id = ?",
                    (codec.seal_profile(key, user), user_id),
                )
            else:
                user = User(
                    user_id=user_id,
                    nick=nick,
                    weight=weight,
                    gender=gender,
                    height=height,
                    read_terms=True,
                    read_announcements=len(ANNOUNCEMENTS),
                    last_active_day=today,
                )
                # a row that is left over from a destroyed key is of no use to anybody
                await tx.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
                await tx.execute(
                    "INSERT INTO users (user_id, profile, drinks) VALUES (?, ?, ?)",
                    (user_id, codec.seal_profile(key, user), codec.seal_drinks(key, user_id, [])),
                )
        return user, existing is None

    async def update_fields(self, user: User, **changes: Any) -> User:
        """Change fields of the profile. Read-modify-write, so that concurrent changes are kept."""
        key = await self._vault.get(user.user_id)
        if key is None:
            raise AccountGone
        async with self._db.transaction() as tx:
            row = await tx.fetchone("SELECT profile FROM users WHERE user_id = ?", (user.user_id,))
            if row is None:
                raise AccountGone
            current = codec.open_profile(key, user.user_id, row["profile"])
            updated = dataclasses.replace(current, **changes)
            await tx.execute(
                "UPDATE users SET profile = ? WHERE user_id = ?",
                (codec.seal_profile(key, updated), user.user_id),
            )
        return updated

    async def update_weight(self, user: User, weight: int) -> None:
        await self.update_fields(user, weight=constants.coarsen(weight, *constants.WEIGHT_RANGE))

    async def update_height(self, user: User, height: int) -> None:
        await self.update_fields(user, height=constants.coarsen(height, *constants.HEIGHT_RANGE))

    async def update_gender(self, user: User, gender: str) -> None:
        await self.update_fields(user, gender=gender)

    async def update_nick(self, user: User, nick: str) -> None:
        await self.update_fields(user, nick=nick)

    async def update_read_announcements(self, user: User, count: int) -> None:
        await self.update_fields(user, read_announcements=count)

    async def touch(self, user: User) -> None:
        """Record that the user is using the bot, which keeps the account from expiring."""
        today = day_number(self._clock())
        if user.last_active_day != today:  # at most one write a day
            try:
                await self.update_fields(user, last_active_day=today)
            except AccountGone:
                pass

    async def delete(self, user: User, *, flush: bool = True) -> None:
        """
        Remove everything about the user. The key goes first: from that moment the data is
        unreadable, even if a copy of it still exists somewhere.
        """
        await self._vault.destroy(user.user_id)
        await self.remove_row(user.user_id)
        if flush:
            await self._db.checkpoint()

    async def remove_row(self, user_id: str) -> None:
        # memberships go with it (ON DELETE CASCADE)
        await self._db.execute("DELETE FROM users WHERE user_id = ?", (user_id,))

    # -- export -------------------------------------------------------------------------------

    async def export(self, telegram_id: int) -> UserData:
        """Everything stored about a user, decrypted, as one table per kind of data."""
        user_id = self._crypto.user_id(telegram_id)
        key = await self._vault.get(user_id)
        empty = UserData(Table([], []), Table([], []), Table([], []))
        if key is None:
            return empty
        async with self._db.transaction() as tx:  # one consistent snapshot
            row = await tx.fetchone(
                "SELECT profile, drinks FROM users WHERE user_id = ?", (user_id,)
            )
            groups = await tx.fetchall(
                "SELECT group_id FROM users_in_groups WHERE user_id = ?", (user_id,)
            )
        if row is None:
            return empty
        user = codec.open_profile(key, user_id, row["profile"])
        drinks = codec.open_drinks(key, user_id, row["drinks"])
        return UserData(
            user=Table(
                [
                    "user_id",
                    "nick",
                    "weight",
                    "height",
                    "gender",
                    "read_terms",
                    "read_announcements",
                    "last_active",
                ],
                [
                    [
                        user.user_id,
                        user.nick,
                        user.weight,
                        user.height,
                        user.gender,
                        int(user.read_terms),
                        user.read_announcements,
                        datetime.fromtimestamp(user.last_active_day * 86400, UTC)
                        .date()
                        .isoformat(),
                    ]
                ],
            ),
            drinks=Table(
                ["created", "alcohol", "description"],
                [
                    [datetime.fromtimestamp(d.created, UTC).isoformat(), d.alcohol, d.description]
                    for d in sorted(drinks, key=lambda d: d.created)
                ],
            ),
            groups=Table(["group_id"], [[g["group_id"]] for g in groups]),
        )
