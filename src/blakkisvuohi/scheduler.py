"""The daily purge."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import datetime as dt
from datetime import timedelta, tzinfo

from .db import PurgeReport, Store

log = logging.getLogger("blakkis.system")

CATCH_UP_AFTER = 24 * 3600  # purge at startup if the last purge is older than this
RETRY_AFTER = 3600  # when a purge failed


def next_run(now: float, hour: int, tz: tzinfo) -> float:
    """The next time (unix) after `now` that it is `hour`:00 local time."""
    local = dt.fromtimestamp(now, tz)
    candidate = local.replace(hour=hour, minute=0, second=0, microsecond=0)
    if candidate <= local:
        candidate = (local + timedelta(days=1)).replace(
            hour=hour, minute=0, second=0, microsecond=0
        )
    return candidate.timestamp()


async def purge_if_due(store: Store, clock: Callable[[], float] = time.time) -> PurgeReport | None:
    """
    Whatever time the bot was started, data older than the retention period must not stay around
    because it happened to be down at noon.
    """
    last = await store.purger.last_run()
    if last is None or clock() - last > CATCH_UP_AFTER:
        return await store.purge()
    return None


async def purge_forever(
    store: Store,
    hour: int,
    tz: tzinfo,
    clock: Callable[[], float] = time.time,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> None:
    """Runs until cancelled. A failing purge is logged and retried; it never stops the bot."""
    delay = 0.0
    try:
        await purge_if_due(store, clock)
    except Exception:
        log.exception("The purge at startup failed")
        delay = RETRY_AFTER
    while True:
        if not delay:
            delay = max(next_run(clock(), hour, tz) - clock(), 1.0)
        log.info("Next purge in %.1f hours", delay / 3600)
        await sleep(delay)
        delay = 0.0
        try:
            await store.purge()
        except Exception:
            log.exception("The purge failed, trying again in an hour")
            delay = RETRY_AFTER
