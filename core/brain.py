"""Implements SPEC §4.2/§4.4: brain-loop delivery — arrive with a plan.

When the judge flags an event dispatchable and it is heading to the user,
prep work runs FIRST and its verified result is merged into the message.
Dispatch timeout 10 min → deliver as-is, never block (SPEC §4.4).
"""

import asyncio
import logging

from core.schema import Event, Task
from core.state import State
from delivery.base import DeliveryMessage
from dispatch.acceptance import AskFn, dispatch_and_verify
from dispatch.executor import Executor

logger = logging.getLogger(__name__)

DISPATCH_TIMEOUT_SECONDS = 600.0  # 10 minutes


async def prepare_delivery(
    state: State,
    event: Event,
    *,
    goal: str,
    acceptance: str,
    executor: Executor,
    ask: AskFn | None = None,
    timeout: float = DISPATCH_TIMEOUT_SECONDS,
) -> tuple[DeliveryMessage, Task]:
    """Dispatch prep work, then build the delivery message with the plan merged in.

    Three outcomes: verified plan attached; timeout → original message as-is;
    dispatch rejected → the ask-the-human text rides along as the plan.
    """
    task = Task(
        id=f"task_{event.id}",
        origin_event_id=event.id,
        goal=goal,
        executor=executor.name,  # type: ignore[arg-type]
        acceptance=acceptance,
    )
    msg = DeliveryMessage(summary=event.summary, event_id=event.id, topic=event.topic)
    try:
        task, ask_human = await asyncio.wait_for(
            dispatch_and_verify(state, task, executor, ask=ask), timeout
        )
        if task.status == "done":
            msg.plan = task.result_summary
        elif ask_human:
            msg.plan = ask_human
    except TimeoutError:
        logger.warning(
            "dispatch for %s exceeded %.0fs; delivering as-is (never block)", event.id, timeout
        )
    return msg, task
