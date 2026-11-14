from __future__ import annotations

import pytest

from blakkisvuohi.db import Store
from blakkisvuohi.security import Crypto

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


@pytest.fixture
async def store(crypto, clock, tmp_path):
    store = await Store.open(tmp_path / "data.sqlite3", tmp_path / "keys.sqlite3", crypto, clock)
    yield store
    await store.close()


@pytest.fixture
async def h(store, tmp_path):
    from harness import make_harness

    return await make_harness(store, tmp_path)
