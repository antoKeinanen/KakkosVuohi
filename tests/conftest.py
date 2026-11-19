from __future__ import annotations

import os

import pytest

if os.environ.get("TEST_LAZY_AIOGRAM"):
    # as in the Worker: aiogram's models are built when first used (workers/lazy_models.py)
    from blakkisvuohi.workers.lazy_models import import_aiogram

    import_aiogram()

from blakkisvuohi.db import D1Database, Store  # noqa: E402
from blakkisvuohi.db.database import DATA_MIGRATIONS, KEY_MIGRATIONS  # noqa: E402
from blakkisvuohi.security import Crypto  # noqa: E402

SECRET = "test-secret-key-that-is-long-enough-0123456789"


class Clock:
    """A controllable clock, so that tests are deterministic."""

    def __init__(self, now: float = 1_762_857_600) -> None:  # 2025-11-11 10:40 UTC
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, hours: float = 0, minutes: float = 0, seconds: float = 0) -> None:
        self.now += hours * 3600 + minutes * 60 + seconds


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def crypto() -> Crypto:
    return Crypto(SECRET)


async def open_d1_store(tmp_path, crypto, clock, policy=None) -> Store:
    """A store on D1 (faked with SQLite files of the same names as the SQLite store's)."""
    from fake_d1 import SqliteD1

    from blakkisvuohi import conversations
    from blakkisvuohi.workers.runtime import UPDATES_TABLE

    db = await D1Database.open(SqliteD1(str(tmp_path / "data.sqlite3")), DATA_MIGRATIONS)
    await db.setup([conversations.TABLE, UPDATES_TABLE])  # as the Worker does
    keydb = await D1Database.open(SqliteD1(str(tmp_path / "keys.sqlite3")), KEY_MIGRATIONS)
    return await Store.from_databases(db, keydb, crypto, clock, policy)


@pytest.fixture(params=["sqlite", "d1"])
def backend(request) -> str:
    """Everything that uses a store runs on both: the SQLite files and (fake) D1."""
    return request.param


@pytest.fixture
async def store(backend, crypto, clock, tmp_path):
    if backend == "d1":
        store = await open_d1_store(tmp_path, crypto, clock)
    else:
        store = await Store.open(
            tmp_path / "data.sqlite3", tmp_path / "keys.sqlite3", crypto, clock
        )
    yield store
    await store.close()


@pytest.fixture
async def h(store, backend, crypto, clock, tmp_path):
    from harness import make_harness

    storage = None
    if backend == "d1":  # as on Workers: conversations in the database
        from blakkisvuohi.conversations import DatabaseStorage

        storage = DatabaseStorage(store.db, store.vault, crypto, clock)
    return await make_harness(store, tmp_path, storage=storage)
