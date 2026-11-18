"""
Cloudflare D1 as the database, behind the same interface as `Database`, so that the repositories
work unchanged.

D1 has no interactive transactions: a `batch()` of statements is atomic, but nothing can be read
in between. A transaction here therefore reads directly and buffers its writes, which are sent as
one batch on commit. To keep the guarantee that the repositories rely on (what a transaction read
is still true when its writes land), every write also increments a version counter, and a trigger
aborts a commit whose transaction started at an older version: some other write came in between.
The caller sees `TransactionConflict`, and nothing of the transaction was written.

The version is per database, not per row. That is plenty: the bot handles one update at a time.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Iterator, Sequence
from contextlib import asynccontextmanager
from typing import Any, Protocol

log = logging.getLogger("blakkis.db")

_CONFLICT = "kakkosvuohi: write conflict"
_MIGRATED = "kakkosvuohi: migrated meanwhile"

# Bookkeeping of this module, created before the migrations. Not part of DATA_MIGRATIONS: the
# SQLite databases do not need it (they have PRAGMA user_version and real transactions).
_SETUP = [
    """
    CREATE TABLE IF NOT EXISTS _d1_state (
        id             INTEGER PRIMARY KEY CHECK (id = 1),
        schema_version INTEGER NOT NULL,
        write_version  INTEGER NOT NULL
    ) STRICT
    """,
    "INSERT OR IGNORE INTO _d1_state (id, schema_version, write_version) VALUES (1, 0, 0)",
    f"""
    CREATE TRIGGER IF NOT EXISTS _d1_write_conflict
    BEFORE UPDATE OF write_version ON _d1_state
    WHEN NEW.write_version != OLD.write_version + 1
    BEGIN
        SELECT RAISE(ABORT, '{_CONFLICT}');
    END
    """,
    # a migration applies only on top of the one before it, also when two isolates race
    f"""
    CREATE TRIGGER IF NOT EXISTS _d1_schema_order
    BEFORE UPDATE OF schema_version ON _d1_state
    WHEN NEW.schema_version != OLD.schema_version + 1
    BEGIN
        SELECT RAISE(ABORT, '{_MIGRATED}');
    END
    """,
]
_BUMP = ("UPDATE _d1_state SET write_version = write_version + 1 WHERE id = 1", ())
_BUMP_FROM = "UPDATE _d1_state SET write_version = ? WHERE id = 1"  # aborts unless old + 1
_VERSION = "SELECT write_version FROM _d1_state WHERE id = 1"


class TransactionConflict(Exception):
    """Another write changed the database during the transaction. Nothing was written."""


class D1Client(Protocol):
    """
    What the backend needs from D1. In the Worker this wraps the D1 binding (`workers/d1.py`); the
    tests use SQLite.
    """

    async def query(self, sql: str, params: Sequence[Any]) -> tuple[list[str], list[list[Any]]]:
        """Column names and rows of one statement."""
        ...

    async def batch(self, statements: Sequence[tuple[str, Sequence[Any]]]) -> list[int]:
        """Runs the statements atomically (all or nothing). Rows changed by each."""
        ...


class Row(Sequence[Any]):
    """A result row, by index or by column name, like sqlite3.Row."""

    __slots__ = ("_columns", "_values")

    def __init__(self, columns: dict[str, int], values: list[Any]) -> None:
        self._columns = columns
        self._values = values

    def __getitem__(self, item: Any) -> Any:
        if isinstance(item, str):
            return self._values[self._columns[item]]
        return self._values[item]

    def __len__(self) -> int:
        return len(self._values)

    def __iter__(self) -> Iterator[Any]:
        return iter(self._values)

    def keys(self) -> list[str]:
        return list(self._columns)


def _statements(script: str) -> list[str]:
    """The statements of a migration. Ours never have a ';' inside a literal or a trigger."""
    return [s.strip() for s in script.split(";") if s.strip()]


def _is_conflict(exc: BaseException) -> bool:
    return _CONFLICT in str(exc)


class D1Transaction:
    """Handed out by D1Database.transaction(): reads go to the database, writes wait for commit."""

    def __init__(self, db: D1Database) -> None:
        self._db = db
        self.writes: list[tuple[str, Sequence[Any]]] = []

    async def execute(self, sql: str, params: Sequence[Any] = ()) -> int:
        """Buffered until commit, so the number of changed rows is not known yet: -1."""
        self.writes.append((sql, tuple(params)))
        return -1

    async def fetchone(self, sql: str, params: Sequence[Any] = ()) -> Row | None:
        return await self._db._fetchone(sql, params)

    async def fetchall(self, sql: str, params: Sequence[Any] = ()) -> list[Row]:
        return await self._db._fetchall(sql, params)


class D1Database:
    def __init__(self, client: D1Client, migrations: list[str]) -> None:
        self._client = client
        self._migrations = migrations
        # transactions of this isolate do not interleave, as with Database
        self._lock = asyncio.Lock()

    @classmethod
    async def open(cls, client: D1Client, migrations: list[str]) -> D1Database:
        db = cls(client, migrations)
        await db._migrate()
        return db

    async def _migrate(self) -> None:
        await self._client.batch([(sql, ()) for sql in _SETUP])
        while True:
            row = await self._fetchone("SELECT schema_version FROM _d1_state WHERE id = 1")
            version = int(row[0]) if row else 0
            if version > len(self._migrations):
                raise RuntimeError(
                    f"Database schema version {version} is newer than this bot supports "
                    f"({len(self._migrations)}). Refusing to start."
                )
            if version == len(self._migrations):
                return
            number = version + 1
            log.info("Applying database migration %d", number)
            try:
                # A batch is atomic, and the version is set first: should two isolates migrate
                # at once, the trigger aborts the second one before any of its statements ran.
                await self._client.batch(
                    [("UPDATE _d1_state SET schema_version = ? WHERE id = 1", (number,)), _BUMP]
                    + [(sql, ()) for sql in _statements(self._migrations[version])]
                )
            except Exception as exc:
                if _MIGRATED not in str(exc):
                    raise
                log.info("Migration %d was applied meanwhile by another isolate", number)

    async def setup(self, statements: Sequence[str]) -> None:
        """
        Idempotent DDL (CREATE ... IF NOT EXISTS) of the tables only the Worker uses. Not a
        migration: the SQLite databases of the long running bot do not get these tables.
        """
        await self._client.batch([(sql, ()) for sql in statements])

    async def close(self) -> None:
        """Nothing to close: the binding belongs to the Worker."""

    async def vacuum(self) -> None:
        """D1 manages its storage itself and does not allow VACUUM."""

    async def checkpoint(self) -> None:
        """D1 manages its storage itself; there is no write-ahead log to flush."""

    # -- statements ----------------------------------------------------------------------------

    async def _fetchall(self, sql: str, params: Sequence[Any] = ()) -> list[Row]:
        columns, rows = await self._client.query(sql, tuple(params))
        index = {name: i for i, name in enumerate(columns)}
        return [Row(index, list(values)) for values in rows]

    async def _fetchone(self, sql: str, params: Sequence[Any] = ()) -> Row | None:
        rows = await self._fetchall(sql, params)
        return rows[0] if rows else None

    async def execute(self, sql: str, params: Sequence[Any] = ()) -> int:
        async with self._lock:
            # a write on its own also moves the version on, so that it conflicts with any
            # transaction that read before it and commits after it
            changes = await self._client.batch([_BUMP, (sql, tuple(params))])
            return changes[1]

    async def fetchone(self, sql: str, params: Sequence[Any] = ()) -> Row | None:
        return await self._fetchone(sql, params)

    async def fetchall(self, sql: str, params: Sequence[Any] = ()) -> list[Row]:
        return await self._fetchall(sql, params)

    async def _version(self) -> int:
        row = await self._fetchone(_VERSION)
        assert row is not None, "the _d1_state row is created when the database is opened"
        return int(row[0])

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[D1Transaction]:
        async with self._lock:
            started = await self._version()
            tx = D1Transaction(self)
            yield tx  # an exception in the block discards the buffered writes
            if not tx.writes:
                # read only: the reads are consistent if nothing was written in between
                if await self._version() != started:
                    raise TransactionConflict
                return
            try:
                await self._client.batch([(_BUMP_FROM, (started + 1,)), *tx.writes])
            except Exception as exc:
                if _is_conflict(exc):
                    raise TransactionConflict from exc
                raise
