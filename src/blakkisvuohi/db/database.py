"""SQLite connection management and schema migrations."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import stat
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import aiosqlite

log = logging.getLogger("blakkis.db")

# Each entry is applied exactly once, in order. Never edit an entry that has been released:
# append a new one. The schema version is kept in PRAGMA user_version.
#
# There are two databases. The data database holds only ciphertext (see security.py):
#   users.user_id    HMAC of the Telegram id
#   users.profile    encrypted: nickname, weight, height, gender, terms, announcements, last use
#   users.drinks     encrypted: all the drinks of the user, as one padded blob
#   users_in_groups  user_id -> HMAC of the chat id (the only thing that is queryable)
DATA_MIGRATIONS: list[str] = [
    """
    CREATE TABLE meta (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
    ) STRICT;

    CREATE TABLE users (
        user_id TEXT PRIMARY KEY,
        profile TEXT NOT NULL,
        drinks  TEXT NOT NULL
    ) STRICT;

    CREATE TABLE users_in_groups (
        user_id  TEXT NOT NULL REFERENCES users (user_id) ON DELETE CASCADE,
        group_id TEXT NOT NULL,
        PRIMARY KEY (user_id, group_id)
    ) STRICT;
    CREATE INDEX users_in_groups_by_group ON users_in_groups (group_id);
    """,
]

# The key database holds the wrapped data key of every user, and nothing else.
KEY_MIGRATIONS: list[str] = [
    """
    CREATE TABLE meta (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
    ) STRICT;

    CREATE TABLE user_keys (
        user_id     TEXT PRIMARY KEY,
        wrapped_key TEXT NOT NULL
    ) STRICT;
    """,
]


def _prepare_path(path: Path) -> None:
    """Make sure that the database is only ever readable by the bot's own user."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not path.exists():
        # create the file with restrictive permissions *before* sqlite gets to create it
        os.close(os.open(path, os.O_CREAT | os.O_WRONLY, 0o600))
    elif stat.S_IMODE(path.stat().st_mode) & 0o077:
        log.warning("Database file %s is accessible by other users, restricting it", path)
        path.chmod(0o600)


class _Queries:
    """The query methods. Subclasses decide about locking."""

    _conn: aiosqlite.Connection

    async def _execute(self, sql: str, params: Sequence[Any] = ()) -> int:
        cursor = await self._conn.execute(sql, params)
        try:
            return cursor.rowcount
        finally:
            await cursor.close()

    async def _fetchone(self, sql: str, params: Sequence[Any] = ()) -> aiosqlite.Row | None:
        async with self._conn.execute(sql, params) as cursor:
            return await cursor.fetchone()  # type: ignore[return-value]

    async def _fetchall(self, sql: str, params: Sequence[Any] = ()) -> list[aiosqlite.Row]:
        async with self._conn.execute(sql, params) as cursor:
            return list(await cursor.fetchall())  # type: ignore[arg-type]


class Transaction(_Queries):
    """Handed out by Database.transaction(); the database lock is already held."""

    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn

    execute = _Queries._execute
    fetchone = _Queries._fetchone
    fetchall = _Queries._fetchall


class Database(_Queries):
    """
    One connection, one lock. Every statement and every transaction takes the lock, so that
    coroutines can never interleave statements into somebody else's transaction. SQLite
    serialises writers anyway, and this scale does not need more.
    """

    def __init__(self, conn: aiosqlite.Connection, migrations: list[str]) -> None:
        self._conn = conn
        self._migrations = migrations
        self._lock = asyncio.Lock()

    @classmethod
    async def open(cls, path: Path | str, migrations: list[str]) -> Database:
        if str(path) != ":memory:":
            _prepare_path(Path(path))
        conn = await aiosqlite.connect(path, isolation_level=None)  # we manage transactions
        conn.row_factory = aiosqlite.Row
        db = cls(conn, migrations)
        await db._configure()
        await db._migrate()
        return db

    async def _configure(self) -> None:
        for pragma in (
            "PRAGMA foreign_keys = ON",
            "PRAGMA journal_mode = WAL",
            "PRAGMA synchronous = NORMAL",
            "PRAGMA busy_timeout = 5000",
            "PRAGMA secure_delete = ON",  # deleted personal data is overwritten, not just unlinked
            "PRAGMA trusted_schema = OFF",
        ):
            await self._conn.execute(pragma)

    async def _migrate(self) -> None:
        async with self._lock:
            async with self._conn.execute("PRAGMA user_version") as cursor:
                row = await cursor.fetchone()
            version = row[0] if row else 0
            if version > len(self._migrations):
                raise RuntimeError(
                    f"Database schema version {version} is newer than this bot supports "
                    f"({len(self._migrations)}). Refusing to start."
                )
            for number, script in enumerate(self._migrations[version:], start=version + 1):
                log.info("Applying database migration %d", number)
                try:
                    await self._conn.executescript(
                        f"BEGIN IMMEDIATE;\n{script}\nPRAGMA user_version = {number};\nCOMMIT;"
                    )
                except BaseException:
                    if self._conn.in_transaction:
                        await self._conn.execute("ROLLBACK")
                    raise

    async def close(self) -> None:
        async with self._lock:
            with contextlib.suppress(Exception):
                await self._conn.execute("PRAGMA optimize")
            await self._conn.close()

    async def vacuum(self) -> None:
        """Rewrite the file without the free pages, so that no trace of deleted rows is left."""
        async with self._lock:
            with contextlib.suppress(Exception):
                await self._conn.execute("VACUUM")

    async def checkpoint(self) -> None:
        """Flush the write-ahead log so that deleted rows really leave the disk."""
        async with self._lock:
            with contextlib.suppress(Exception):
                await self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    # -- locked single statements --------------------------------------------------------------

    async def execute(self, sql: str, params: Sequence[Any] = ()) -> int:
        async with self._lock:
            return await self._execute(sql, params)

    async def fetchone(self, sql: str, params: Sequence[Any] = ()) -> aiosqlite.Row | None:
        async with self._lock:
            return await self._fetchone(sql, params)

    async def fetchall(self, sql: str, params: Sequence[Any] = ()) -> list[aiosqlite.Row]:
        async with self._lock:
            return await self._fetchall(sql, params)

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[Transaction]:
        async with self._lock:
            await self._conn.execute("BEGIN IMMEDIATE")
            try:
                yield Transaction(self._conn)
            except BaseException:
                await self._conn.execute("ROLLBACK")
                raise
            else:
                await self._conn.execute("COMMIT")
