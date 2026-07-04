"""Step 14 acceptance: fake-executor lifecycle tests pending→running→done/failed;
shell whitelist rejects non-template commands."""

import json

import pytest

from core.schema import Task
from core.state import State
from dispatch.executor import (
    SHELL_TEMPLATES,
    ClaudeCodeExecutor,
    ShellExecutor,
    build_shell_command,
    run_task,
)


def task(**kw):
    defaults = dict(
        id="task_1",
        origin_event_id="evt_x",
        goal="fix the failing test",
        executor="claude_code",
        acceptance="CI green",
    )
    defaults.update(kw)
    return Task(**defaults)


# --- lifecycle ---


class FakeExecutor:
    name = "fake"

    def __init__(self, result="did it", fail=False):
        self.result, self.fail = result, fail
        self.seen_status: str | None = None

    async def run(self, t: Task) -> str:
        self.seen_status = t.status  # must be "running" mid-flight
        if self.fail:
            raise RuntimeError("boom")
        return self.result


async def test_lifecycle_pending_running_done(tmp_path):
    async with State.open(tmp_path / "s.db") as state:
        t = task()
        assert t.status == "pending"
        fake = FakeExecutor()
        done = await run_task(state, t, fake)
        assert fake.seen_status == "running"
        assert done.status == "done" and done.result_summary == "did it"
        assert done.attempts == 1
        assert (await state.load_task("task_1")).status == "done"


async def test_lifecycle_failure(tmp_path):
    async with State.open(tmp_path / "s.db") as state:
        done = await run_task(state, task(), FakeExecutor(fail=True))
        assert done.status == "failed"
        assert done.attempts == 1
        assert (await state.load_task("task_1")).status == "failed"


async def test_attempts_accumulate(tmp_path):
    async with State.open(tmp_path / "s.db") as state:
        t = task()
        await run_task(state, t, FakeExecutor(fail=True))
        await run_task(state, t, FakeExecutor())
        assert t.attempts == 2 and t.status == "done"


# --- shell whitelist (SPEC §4.5: query-only templates, arbitrary shell forbidden) ---


def test_templates_are_query_only():
    forbidden = {"rm", "mv", "dd", "sudo", "sh", "bash", "eval", "curl -X POST"}
    for argv in SHELL_TEMPLATES.values():
        assert argv[0] not in forbidden


def test_build_shell_command_fills_placeholders():
    argv = build_shell_command("git_log", {"path": "/repo"})
    assert argv == ["git", "-C", "/repo", "log", "--oneline", "-20"]


def test_unknown_template_rejected():
    with pytest.raises(ValueError, match="not in the whitelist"):
        build_shell_command("rm_rf", {"path": "/"})


def test_raw_command_rejected():
    with pytest.raises(ValueError, match="not in the whitelist"):
        build_shell_command("rm -rf /", {})


def test_missing_arg_rejected():
    with pytest.raises(KeyError):
        build_shell_command("git_log", {})


def test_injection_stays_single_argv():
    argv = build_shell_command("git_log", {"path": "/repo; rm -rf /"})
    assert argv[2] == "/repo; rm -rf /"  # one argv element, never a shell string


async def test_shell_executor_runs_template():
    ex = ShellExecutor()
    t = task(executor="shell", goal=json.dumps({"template": "echo_test", "args": {"text": "ok"}}))
    out = await ex.run(t)
    assert out.strip() == "ok"


async def test_shell_executor_rejects_freeform_goal():
    ex = ShellExecutor()
    with pytest.raises(ValueError):
        await ex.run(task(executor="shell", goal="rm -rf /"))


# --- claude_code executor (subprocess mocked) ---


async def test_claude_code_executor_builds_prompt(tmp_path):
    calls = {}

    async def fake_exec(argv, cwd):
        calls["argv"], calls["cwd"] = argv, cwd
        return 0, json.dumps({"result": "patched, PR opened"}), ""

    ex = ClaudeCodeExecutor(workdir=str(tmp_path), exec_fn=fake_exec)
    out = await ex.run(task())
    assert out == "patched, PR opened"
    assert calls["argv"][0] == "claude"
    assert "-p" in calls["argv"]
    prompt = calls["argv"][calls["argv"].index("-p") + 1]
    assert "fix the failing test" in prompt and "Acceptance: CI green" in prompt
    assert "--output-format" in calls["argv"]
    assert calls["cwd"] == str(tmp_path)


async def test_claude_code_executor_nonzero_exit_fails(tmp_path):
    async def fake_exec(argv, cwd):
        return 1, "", "exploded"

    ex = ClaudeCodeExecutor(workdir=str(tmp_path), exec_fn=fake_exec)
    with pytest.raises(RuntimeError, match="exploded"):
        await ex.run(task())
