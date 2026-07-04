"""Implements SPEC §4.1: built-in source scaffolding — pure fetch→Event→submit
coroutines with interval discipline. No judgment logic in sources."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

logger = logging.getLogger(__name__)


class Poller:
    """Calls `fetch` at most once per interval and submits every payload
    through the unified entry (`submit` is usually Brain.process)."""

    def __init__(
        self,
        fetch: Callable[[], Awaitable[list[dict]]],
        submit: Callable[[dict], Awaitable],
        interval_minutes: float,
        name: str = "poller",
    ):
        self.fetch = fetch
        self.submit = submit
        self.interval = timedelta(minutes=interval_minutes)
        self.name = name
        self._last_fetch: datetime | None = None

    async def tick(self, now: datetime) -> None:
        if self._last_fetch and now - self._last_fetch < self.interval:
            return
        self._last_fetch = now
        try:
            payloads = await self.fetch()
        except Exception as exc:
            logger.warning("%s fetch failed: %s", self.name, exc)
            return
        for payload in payloads:
            try:
                await self.submit(payload)
            except Exception as exc:
                logger.warning("%s submit failed: %s", self.name, exc)

    async def run(self, stop: asyncio.Event | None = None) -> None:
        stop = stop or asyncio.Event()
        while not stop.is_set():
            await self.tick(datetime.now(UTC))
            try:
                await asyncio.wait_for(stop.wait(), timeout=30)
            except TimeoutError:
                pass
