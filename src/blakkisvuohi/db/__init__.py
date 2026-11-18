"""Persistence: two databases (SQLite files or D1), one for the (encrypted) data, one for the keys."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from ..security import Crypto
from .d1 import D1Database, TransactionConflict
from .database import DATA_MIGRATIONS, KEY_MIGRATIONS, Database
from .drinks import DrinkRepository, LateDrink, TooManyDrinks
from .groups import GroupRepository
from .models import PurgeReport, RetentionPolicy
from .retention import Purger
from .stats import StatsRepository
from .users import AccountGone, UserRepository
from .vault import Vault


class WrongSecretKey(Exception):
    """The databases were created with a different SECRET_KEY."""


class Store:
    """Everything the handlers need to read and write data."""

    def __init__(
        self,
        db: Database,
        keydb: Database,
        crypto: Crypto,
        clock: Callable[[], float] = time.time,
        policy: RetentionPolicy | None = None,
    ) -> None:
        policy = policy or RetentionPolicy()
        self.db = db
        self.keydb = keydb
        self.crypto = crypto
        self.policy = policy
        self.vault = Vault(keydb, crypto, clock)
        self.users = UserRepository(db, self.vault, crypto, clock, policy)
        self.drinks = DrinkRepository(db, self.vault, clock, policy)
        self.groups = GroupRepository(db, crypto, self.users, clock)
        self.stats = StatsRepository(db, crypto, self.users, self.groups, clock)
        self.purger = Purger(db, keydb, self.vault, self.users, self.drinks, policy, clock)

    @classmethod
    async def open(
        cls,
        path: Path | str,
        key_path: Path | str,
        crypto: Crypto,
        clock: Callable[[], float] = time.time,
        policy: RetentionPolicy | None = None,
    ) -> Store:
        if str(path) == str(key_path):
            raise ValueError("the data and the keys must be in different database files")
        db = await Database.open(path, DATA_MIGRATIONS)
        try:
            keydb = await Database.open(key_path, KEY_MIGRATIONS)
        except BaseException:
            await db.close()
            raise
        return await cls.from_databases(db, keydb, crypto, clock, policy)

    @classmethod
    async def from_databases(
        cls,
        db: Database | D1Database,
        keydb: Database | D1Database,
        crypto: Crypto,
        clock: Callable[[], float] = time.time,
        policy: RetentionPolicy | None = None,
    ) -> Store:
        """A store on databases that are already open and migrated, e.g. the D1 ones."""
        store = cls(db, keydb, crypto, clock, policy)  # type: ignore[arg-type]
        try:
            await store._initialise()
        except BaseException:
            await store.close()
            raise
        return store

    async def _initialise(self) -> None:
        """
        Pseudonymous ids and encryption depend on SECRET_KEY. Starting with another key would
        silently make every user look new and orphan all stored data, so refuse instead.
        """
        expected = self.crypto.key_check()
        for database in (self.db, self.keydb):
            row = await database.fetchone("SELECT value FROM meta WHERE key = 'key_check'")
            if row is None:
                await database.execute(
                    "INSERT INTO meta (key, value) VALUES ('key_check', ?)", (expected,)
                )
            elif row["value"] != expected:
                raise WrongSecretKey(
                    "SECRET_KEY does not match the one the databases were created with. "
                    "Refusing to start: the stored data would be unreadable."
                )
        for counter in ("drinks_total", "alcohol_total"):
            # only when missing: on D1 every write makes other transactions in flight start over
            if await self.db.fetchone("SELECT 1 FROM meta WHERE key = ?", (counter,)) is None:
                await self.db.execute(
                    "INSERT OR IGNORE INTO meta (key, value) VALUES (?, '0')", (counter,)
                )

    async def purge(self) -> PurgeReport:
        return await self.purger.run()

    async def close(self) -> None:
        await self.db.close()
        await self.keydb.close()


__all__ = [
    "AccountGone",
    "D1Database",
    "Database",
    "LateDrink",
    "PurgeReport",
    "RetentionPolicy",
    "Store",
    "TooManyDrinks",
    "TransactionConflict",
    "WrongSecretKey",
]
