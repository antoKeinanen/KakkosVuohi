"""
Conversation state (a half-finished /juoma or /tunnus, the /start menu) in the data database.

The long running bot keeps it in memory. A Worker cannot: every request may run in a fresh
isolate. The state can hold personal details (drinks the menu offers again, weight and height on
their way into an account), so it is stored like the rest: under a pseudonymous id, and sealed
with the user's own key, so that deleting the account shreds it too. Before signing up a user has
no key yet; their state is sealed with a key derived from SECRET_KEY. The purge deletes the state
of conversations that have not moved for two days.
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

    async def _read(self, key: StorageKey) -> tuple[str | None, dict[str, Any]]:
        row_id = self._id(key)
        row = await self._db.fetchone("SELECT value FROM conversations WHERE id = ?", (row_id,))
        if row is None:
            return None, {}
        kind, sealed = row["value"][:2], row["value"][2:]
        data_key = await self._user_key(key) if kind == _USER else self._crypto.conversation_key
        if data_key is None:
            return None, {}  # the account (and its key) was deleted: the state is gone with it
        try:
            value = data_key.open(sealed, aad=f"{row_id}:conversation")
        except DecryptionError:
            return None, {}  # sealed with a key the user no longer has: as good as gone
        return value["state"], value["data"]

    async def _write(self, key: StorageKey, state: str | None, data: dict[str, Any]) -> None:
        row_id = self._id(key)
        if state is None and not data:
            await self._db.execute("DELETE FROM conversations WHERE id = ?", (row_id,))
            return
        user_key = await self._user_key(key)
        kind, data_key = (_USER, user_key) if user_key else (_SIGNUP, self._crypto.conversation_key)
        sealed = data_key.seal({"state": state, "data": data}, aad=f"{row_id}:conversation")
        await self._db.execute(
            "INSERT INTO conversations (id, value, day) VALUES (?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET value = excluded.value, day = excluded.day",
            (row_id, kind + sealed, day_number(self._clock())),
        )

    async def set_state(self, key: StorageKey, state: StateType = None) -> None:
        _, data = await self._read(key)
        await self._write(key, state.state if isinstance(state, State) else state, data)

    async def get_state(self, key: StorageKey) -> str | None:
        return (await self._read(key))[0]

    async def set_data(self, key: StorageKey, data: Mapping[str, Any]) -> None:
        if not isinstance(data, dict):
            msg = f"Data must be a dict or dict-like object, got {type(data).__name__}"
            raise DataNotDictLikeError(msg)
        state, _ = await self._read(key)
        await self._write(key, state, dict(data))

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        return (await self._read(key))[1]

    async def close(self) -> None:
        """The database belongs to the store."""
