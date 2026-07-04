"""Step 15 acceptance: acceptance_cmd pass/fail paths; LLM-verifier fail →
retry → downgrade produces an interrupt asking the human."""

import json

from core.schema import Task
from core.state import State
from dispatch.acceptance import dispatch_and_verify, verify


def task(**kw):
    defaults = dict(
        id="task_1",
        origin_event_id="evt_x",
        goal="fix the failing test",
        executor="claude_code",
        acceptance="CI green",
        result_summary="patched",
    )
    defaults.update(kw)
    return Task(**defaults)


# --- acceptance_cmd: exit 0 = pass (SPEC §4.5) ---


async def test_acceptance_cmd_pass():
    v = await verify(task(acceptance_cmd="true"))
    assert v.passed


async def test_acceptance_cmd_fail():
    v = await verify(task(acceptance_cmd="false"))
    assert not v.passed
    assert "exit" in v.reason


# --- LLM second opinion ---


async def test_llm_second_opinion_pass():
    async def ask(prompt: str) -> str:
        assert "CI green" in prompt and "patched" in prompt
        return json.dumps({"verdict": "pass", "reason": "matches criteria"})

    v = await verify(task(), ask=ask)
    assert v.passed and v.reason == "matches criteria"


async def test_llm_second_opinion_fail():
    async def ask(prompt: str) -> str:
        return json.dumps({"verdict": "fail", "reason": "tests still red"})

    v = await verify(task(), ask=ask)
    assert not v.passed


async def test_llm_verifier_defaults_to_fail_on_garbage():
    async def ask(prompt: str) -> str:
        return "shrug"

    v = await verify(task(), ask=ask)
    assert not v.passed  # done is a claim, not a proof


# --- retry once, then downgrade to interrupt asking the human ---


class FlakyExecutor:
    name = "fake"

    def __init__(self, results: list[str]):
        self.results = list(results)

    async def run(self, t: Task) -> str:
        return self.results.pop(0)


async def test_verify_fail_retry_pass(tmp_path):
    async with State.open(tmp_path / "s.db") as state:
        seen = []

        async def ask(prompt: str) -> str:
            verdict = "fail" if not seen else "pass"
            seen.append(1)
            return json.dumps({"verdict": verdict, "reason": "x"})

        t, ask_human = await dispatch_and_verify(
            state, task(result_summary=None), FlakyExecutor(["half done", "done properly"]), ask=ask
        )
        assert t.status == "done" and t.attempts == 2
        assert ask_human is None


async def test_verify_fail_twice_downgrades_to_ask_human(tmp_path):
    async with State.open(tmp_path / "s.db") as state:
        async def ask(prompt: str) -> str:
            return json.dumps({"verdict": "fail", "reason": "acceptance unmet"})

        t, ask_human = await dispatch_and_verify(
            state, task(result_summary=None), FlakyExecutor(["nope", "still nope"]), ask=ask
        )
        assert t.status == "rejected"
        assert t.attempts == 2
        assert ask_human is not None
        assert "fix the failing test" in ask_human  # the human sees the goal
        assert (await state.load_task("task_1")).status == "rejected"


async def test_executor_failure_also_downgrades(tmp_path):
    class Exploder:
        name = "boom"

        async def run(self, t):
            raise RuntimeError("no network")

    async with State.open(tmp_path / "s.db") as state:
        t, ask_human = await dispatch_and_verify(state, task(result_summary=None), Exploder())
        assert t.status == "rejected" and ask_human is not None
