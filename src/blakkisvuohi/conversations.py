"""
Conversation state (a half-finished /juoma or /tunnus, the /start menu) in the data database.

The long running bot keeps it in memory. A Worker cannot: every request may run in a fresh
isolate. The state can hold personal details (drinks the menu offers again, weight and height on
their way into an account), so it is stored like the rest: under a pseudonymous id, and sealed
with the user's own key, so that deleting the account shreds it too. Before signing up a user has
no key yet; their state is sealed with a key derived from SECRET_KEY. After the daily purge the
Worker deletes the state of conversations that have not moved for two days (end_stopped()).

The table belongs to the Worker (created with Database.setup()); the long running bot keeps
conversations in memory and its databases do not have it.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
from typing import Any

from aiogram.exceptions import DataNotDictLikeError
from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, StateType, StorageKey

from .db.d1 import D1Database
from .db.database import Database
from .db.models import day_number
from .db.vault import Vault
from .security import Crypto, DataKey, DecryptionError

_USER = "u:"  # sealed with the user's key
_SIGNUP = "s:"  # sealed with the key derived from SECRET_KEY: the user has no account (yet)

#   id     HMAC of the bot, chat and user ids
#   value  encrypted: the state and its data
#   day    of the last change, for end_stopped()
TABLE = """
CREATE TABLE IF NOT EXISTS conversations (
    id    TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    day   INTEGER NOT NULL
) STRICT
"""
# Unfinished conversations are kept today and yesterday, so one does not end at midnight
KEEP_DAYS = 2


async def end_stopped(db: Database | D1Database, now: float) -> None:
    """Deletes the conversations that have not moved for KEEP_DAYS."""
    await db.execute("DELETE FROM conversations WHERE day <= ?", (day_number(now) - KEEP_DAYS,))


class DatabaseStorage(BaseStorage):
    def __init__(
        self,
        db: Database | D1Database,
        vault: Vault,
        crypto: Crypto,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._db = db
        self._vault = vault
        self._crypto = crypto
        self._clock = clock

    def _id(self, key: StorageKey) -> str:
        parts = [
            key.bot_id,
            key.chat_id,
            key.user_id,
            key.thread_id,
            key.business_connection_id,
            key.destiny,
        ]
        return self._crypto.conversation_id(json.dumps(parts, separators=(",", ":")))

    async def _user_key(self, key: StorageKey) -> DataKey | None:
        return await self._vault.get(self._crypto.user_id(key.user_id))

    async def _read(self, key: StorageKey) -> tuple[str | None, dict[str, Any], bool]:
        """The state, its data, and whether they were sealed with the user's key."""
        row_id = self._id(key)
        row = await self._db.fetchone("SELECT value FROM conversations WHERE id = ?", (row_id,))
        if row is None:
            return None, {}, False
        kind, sealed = row["value"][:2], row["value"][2:]
        of_account = kind == _USER
        data_key = await self._user_key(key) if of_account else self._crypto.conversation_key
        if data_key is None:
            return None, {}, True  # the account (and its key) was deleted: the state with it
        try:
            value = data_key.open(sealed, aad=f"{row_id}:conversation")
        except DecryptionError:
            return None, {}, of_account  # sealed with a key the user no longer has: gone
        return value["state"], value["data"], of_account

    async def _write(
        self, key: StorageKey, state: str | None, data: dict[str, Any], *, of_account: bool
    ) -> None:
        """`of_account`: the data was read from state sealed with the user's key."""
        row_id = self._id(key)
        user_key = await self._user_key(key) if state is not None or data else None
        if (state is None and not data) or (of_account and user_key is None):
            # nothing to keep, or the account was deleted meanwhile: what came from it must not
            # be sealed again with a key that deleting the account does not destroy
            await self._db.execute("DELETE FROM conversations WHERE id = ?", (row_id,))
            return
        kind, data_key = (_USER, user_key) if user_key else (_SIGNUP, self._crypto.conversation_key)
        sealed = data_key.seal({"state": state, "data": data}, aad=f"{row_id}:conversation")
        await self._db.execute(
            "INSERT INTO conversations (id, value, day) VALUES (?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET value = excluded.value, day = excluded.day",
            (row_id, kind + sealed, day_number(self._clock())),
        )

    async def set_state(self, key: StorageKey, state: StateType = None) -> None:
        _, data, of_account = await self._read(key)
        new_state = state.state if isinstance(state, State) else state
        # only data that came out of the account must go with it: a new state may be written
        await self._write(key, new_state, data, of_account=of_account and bool(data))

    async def get_state(self, key: StorageKey) -> str | None:
        return (await self._read(key))[0]

    async def set_data(self, key: StorageKey, data: Mapping[str, Any]) -> None:
        if not isinstance(data, dict):
            msg = f"Data must be a dict or dict-like object, got {type(data).__name__}"
            raise DataNotDictLikeError(msg)
        state, _, of_account = await self._read(key)
        await self._write(key, state, dict(data), of_account=of_account)

    async def update_data(self, key: StorageKey, data: Mapping[str, Any]) -> dict[str, Any]:
        # One read for both the data and where it came from (aiogram's own update_data reads
        # twice, and the account could be deleted in between)
        state, current, of_account = await self._read(key)
        from_account = of_account and bool(current)
        current.update(data)
        await self._write(key, state, current, of_account=from_account)
        return current.copy()

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        return (await self._read(key))[1]

    async def close(self) -> None:
        """The database belongs to the store."""
