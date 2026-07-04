"""Step 16 acceptance: timeout test (mock slow executor) delivers the original
within the deadline; happy path shows the plan in the message."""

import asyncio
import time
from datetime import UTC, datetime

from core.brain import prepare_delivery
from core.schema import Event
from core.state import State

NOW = datetime(2026, 7, 6, 14, 0, tzinfo=UTC)


def ev():
    return Event(
        id="evt_x",
        source="flight-watcher",
        topic="travel.flight_change",
        summary="Flight CA1857 delayed 2.5h",
        received_at=NOW,
    )


class InstantExecutor:
    name = "noop"

    async def run(self, task):
        return "3 rebooking options found. Recommend MU5137 19:05."


class SlowExecutor:
    name = "noop"

    async def run(self, task):
        await asyncio.sleep(30)
        return "too late to matter"


class FailingExecutor:
    name = "noop"

    async def run(self, task):
        raise RuntimeError("no browser session")


async def ask_pass(prompt: str) -> str:
    return '{"verdict": "pass", "reason": "ok"}'


async def test_happy_path_message_carries_plan(tmp_path):
    async with State.open(tmp_path / "s.db") as state:
        msg, task = await prepare_delivery(
            state, ev(), goal="find rebooking options", acceptance="3 options listed",
            executor=InstantExecutor(), ask=ask_pass,
        )
        assert msg.plan == "3 rebooking options found. Recommend MU5137 19:05."
        assert msg.summary == "Flight CA1857 delayed 2.5h"
        assert task.status == "done"
        assert (await state.load_task(task.id)).status == "done"


async def test_timeout_delivers_original_never_blocks(tmp_path):
    async with State.open(tmp_path / "s.db") as state:
        start = time.monotonic()
        msg, task = await prepare_delivery(
            state, ev(), goal="find rebooking options", acceptance="3 options",
            executor=SlowExecutor(), ask=ask_pass, timeout=0.1,
        )
        elapsed = time.monotonic() - start
        assert elapsed < 2, "delivery must not block on a slow dispatch"
        assert msg.plan is None  # delivered as-is
        assert msg.summary == "Flight CA1857 delayed 2.5h"


async def test_failed_dispatch_asks_the_human_in_the_message(tmp_path):
    async with State.open(tmp_path / "s.db") as state:
        msg, task = await prepare_delivery(
            state, ev(), goal="find rebooking options", acceptance="3 options",
            executor=FailingExecutor(), ask=ask_pass,
        )
        assert task.status == "rejected"
        assert msg.plan and "couldn't finish this myself" in msg.plan
