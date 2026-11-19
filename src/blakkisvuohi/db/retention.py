"""The purge: physically deletes what is past the retention period."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from .database import Database
from .drinks import DrinkRepository
from .models import PurgeReport, RetentionPolicy, day_number
from .users import UserRepository
from .vault import Vault

log = logging.getLogger("blakkis.db")


class Purger:
    def __init__(
        self,
        db: Database,
        keydb: Database,
        vault: Vault,
        users: UserRepository,
        drinks: DrinkRepository,
        policy: RetentionPolicy,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._db = db
        self._keydb = keydb
        self._vault = vault
        self._users = users
        self._drinks = drinks
        self._policy = policy
        self._clock = clock

    async def last_run(self) -> float | None:
        row = await self._db.fetchone("SELECT value FROM meta WHERE key = 'last_purge'")
        return float(row["value"]) if row else None

    async def run(self) -> PurgeReport:
        """
        * deletes the drinks older than the retention period
        * deletes the accounts that have not been used for that long
        * removes leftovers: data without a key (it cannot be read by anyone) and keys without data
          (unless the key was taken into use since yesterday: the data may be on its way)
        * rewrites the database files, so that no trace of deleted rows is left in them
        """
        started = time.monotonic()
        now = self._clock()
        last = await self.last_run()
        if last is not None and now < last:
            # a clock that went backwards says nothing sensible about what is old
            raise RuntimeError(
                "the system clock is earlier than at the previous purge; not purging"
            )

        report = PurgeReport()
        data_ids = {r[0] for r in await self._db.fetchall("SELECT user_id FROM users")}
        key_ids = await self._vault.all_ids()
        for user_id in data_ids - key_ids:
            await self._users.remove_row(user_id)
            report.orphans_removed += 1
        # A key without data may belong to somebody who is signing up right now: the key is
        # created a moment before the data. Keys taken into use today or yesterday stay.
        for user_id in key_ids - data_ids:
            if await self._vault.destroy_unclaimed(user_id, day_number(now) - 1):
                report.orphans_removed += 1

        stale_before = self._policy.account_cutoff_day(now)
        async for account in self._users.scan():
            report.accounts_scanned += 1
            if account.user.last_active_day < stale_before:
                await self._users.delete(account.user, flush=False)
                report.accounts_deleted += 1
                report.drinks_deleted += len(account.drinks) + account.expired_drinks
            elif account.expired_drinks:
                report.drinks_deleted += await self._drinks.trim(account.user.user_id, account.key)

        for db in (self._db, self._keydb):
            await db.checkpoint()
            await db.vacuum()
        await self._db.execute(
            "INSERT INTO meta (key, value) VALUES ('last_purge', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (str(now),),
        )
        report.seconds = time.monotonic() - started
        log.info(
            "Purge: scanned %d accounts, deleted %d accounts and %d drinks, removed %d leftovers",
            report.accounts_scanned,
            report.accounts_deleted,
            report.drinks_deleted,
            report.orphans_removed,
        )
        return report
