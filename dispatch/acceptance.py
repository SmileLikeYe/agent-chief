"""Implements SPEC §4.5: dispatch verification — "done" is a claim, not a proof.

acceptance_cmd present → run it, exit 0 = pass; else LLM second opinion.
fail → retry once → fail again → downgrade to an interrupt asking the human.
"""

import json
import logging
import shlex
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from core.schema import Task
from core.state import State
from dispatch.executor import Executor, _default_exec, run_task
from judge.base import extract_json
from judge.prompts import VERIFY_PROMPT

logger = logging.getLogger(__name__)

AskFn = Callable[[str], Awaitable[str]]


@dataclass
class VerifyResult:
    passed: bool
    reason: str


async def verify(
    task: Task, *, ask: AskFn | None = None, exec_fn: Callable = _default_exec
) -> VerifyResult:
    """Check a completed task against its acceptance criteria."""
    if task.acceptance_cmd:
        argv = shlex.split(task.acceptance_cmd)
        code, _out, err = await exec_fn(argv, None)
        if code == 0:
            return VerifyResult(True, "acceptance_cmd exit 0")
        return VerifyResult(False, f"acceptance_cmd exit {code}: {err.strip()[:120]}")

    if ask is None:
        # No verifier available: never bless unverified work.
        return VerifyResult(False, "no verifier configured; refusing to trust the claim")

    prompt = VERIFY_PROMPT.format(
        acceptance=task.acceptance, result=task.result_summary or "(no result)"
    )
    raw = await ask(prompt)
    try:
        data = json.loads(extract_json(raw))
        return VerifyResult(data.get("verdict") == "pass", data.get("reason", ""))
    except Exception:
        logger.warning("verifier returned garbage; treating as fail: %r", raw[:80])
        return VerifyResult(False, "verifier output unparseable")


async def dispatch_and_verify(
    state: State,
    task: Task,
    executor: Executor,
    *,
    ask: AskFn | None = None,
    exec_fn: Callable = _default_exec,
) -> tuple[Task, str | None]:
    """Run + verify with one retry (attempts max 2, SPEC §3); on final failure
    mark the task rejected and return a message asking the human."""
    last_reason = ""
    while task.attempts < 2:
        task = await run_task(state, task, executor)
        if task.status == "done":
            result = await verify(task, ask=ask, exec_fn=exec_fn)
            if result.passed:
                return task, None
            last_reason = result.reason
            task.status = "failed"
            await state.save_task(task)
        else:
            last_reason = task.result_summary or "executor failed"

    task.status = "rejected"
    await state.save_task(task)
    ask_human = (
        f"I tried twice and couldn't finish this myself: {task.goal}\n"
        f"Last attempt: {task.result_summary}\n"
        f"Why it didn't pass: {last_reason}\n"
        f"Can you take a look?"
    )
    return task, ask_human
