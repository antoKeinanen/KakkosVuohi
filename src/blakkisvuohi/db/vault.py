"""The data keys of the users, in the key database."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable, Sequence

from ..security import Crypto, DataKey, DecryptionError
from .database import Database
from .models import day_number

log = logging.getLogger("blakkis.db")
_CHUNK = 500


class Vault:
    def __init__(
        self, db: Database, crypto: Crypto, clock: Callable[[], float] = time.time
    ) -> None:
        self._db = db
        self._crypto = crypto
        self._clock = clock

    async def get(self, user_id: str) -> DataKey | None:
        row = await self._db.fetchone(
            "SELECT wrapped_key FROM user_keys WHERE user_id = ?", (user_id,)
        )
        return self._crypto.unwrap(row["wrapped_key"], user_id) if row else None

    async def get_many(self, user_ids: Sequence[str]) -> dict[str, DataKey]:
        keys: dict[str, DataKey] = {}
        for i in range(0, len(user_ids), _CHUNK):
            chunk = list(user_ids[i : i + _CHUNK])
            rows = await self._db.fetchall(
                "SELECT user_id, wrapped_key FROM user_keys "
                "WHERE user_id IN (SELECT value FROM json_each(?))",
                (json.dumps(chunk),),
            )
            for row in rows:
                try:
                    keys[row["user_id"]] = self._crypto.unwrap(row["wrapped_key"], row["user_id"])
                except DecryptionError:
                    log.error("A data key cannot be unwrapped, skipping the account")
        return keys

    async def create(self, user_id: str) -> DataKey:
        """
        The user's key; a new one is made when they have none. Never replaces a key. The key is
        marked as taken today, so that the purge leaves it alone until the data is written.
        """
        today = day_number(self._clock())
        async with self._db.transaction() as tx:
            row = await tx.fetchone(
                "SELECT wrapped_key FROM user_keys WHERE user_id = ?", (user_id,)
            )
            if row:
                await tx.execute(
                    "UPDATE user_keys SET claimed_day = ? WHERE user_id = ?", (today, user_id)
                )
                return self._crypto.unwrap(row["wrapped_key"], user_id)
            key = self._crypto.new_data_key()
            await tx.execute(
                "INSERT INTO user_keys (user_id, wrapped_key, claimed_day) VALUES (?, ?, ?)",
                (user_id, self._crypto.wrap(key, user_id), today),
            )
            return key

    async def destroy(self, user_id: str) -> None:
        """Without its key, the user's data is gone for good, wherever copies of it may be."""
        await self._db.execute("DELETE FROM user_keys WHERE user_id = ?", (user_id,))

    async def destroy_unclaimed(self, user_id: str, before_day: int) -> bool:
        """Destroys the key unless it was taken into use on `before_day` or later."""
        changes = await self._db.execute(
            "DELETE FROM user_keys WHERE user_id = ? AND claimed_day < ?", (user_id, before_day)
        )
        return changes > 0

    async def all_ids(self) -> set[str]:
        return {r[0] for r in await self._db.fetchall("SELECT user_id FROM user_keys")}
