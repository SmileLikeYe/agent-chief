"""Implements SPEC §4.5: dispatch executors — task lifecycle, claude_code
subprocess, query-only shell whitelist. Arbitrary shell is forbidden (SPEC §13)."""

import asyncio
import json
from collections.abc import Callable
from typing import Protocol

from core.schema import Task
from core.state import State


class Executor(Protocol):
    name: str

    async def run(self, task: Task) -> str: ...


async def run_task(state: State, task: Task, executor: Executor) -> Task:
    """One lifecycle pass: pending/failed → running → done/failed, persisted."""
    task.status = "running"
    task.attempts += 1
    await state.save_task(task)
    try:
        task.result_summary = await executor.run(task)
        task.status = "done"
    except Exception as exc:
        task.result_summary = f"{type(exc).__name__}: {exc}"
        task.status = "failed"
    await state.save_task(task)
    return task


class NoopExecutor:
    name = "noop"

    async def run(self, task: Task) -> str:
        return "noop: no work performed"


async def _default_exec(argv: list[str], cwd: str | None) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        *argv, cwd=cwd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    out, err = await proc.communicate()
    return proc.returncode or 0, out.decode(), err.decode()


class ClaudeCodeExecutor:
    """`claude -p "{goal}\\nAcceptance: {acceptance}" --output-format json` (SPEC §4.5)."""

    name = "claude_code"

    def __init__(self, workdir: str | None = None, exec_fn: Callable = _default_exec):
        self.workdir = workdir
        self.exec_fn = exec_fn

    async def run(self, task: Task) -> str:
        prompt = f"{task.goal}\nAcceptance: {task.acceptance}"
        argv = ["claude", "-p", prompt, "--output-format", "json"]
        code, out, err = await self.exec_fn(argv, self.workdir)
        if code != 0:
            raise RuntimeError(f"claude_code exited {code}: {err.strip() or out.strip()}")
        try:
            return json.loads(out).get("result", out.strip())
        except json.JSONDecodeError:
            return out.strip()


# Query-only command templates. Values are argv lists; {placeholders} are filled
# from task args as single argv elements — never joined into a shell string.
SHELL_TEMPLATES: dict[str, list[str]] = {
    "git_status": ["git", "-C", "{path}", "status", "--short"],
    "git_log": ["git", "-C", "{path}", "log", "--oneline", "-20"],
    "gh_notifications": ["gh", "api", "notifications"],
    "gh_pr_view": ["gh", "pr", "view", "{number}", "--json", "title,state,url"],
    "http_head": ["curl", "-sI", "--max-time", "10", "{url}"],
    "echo_test": ["echo", "{text}"],
}


def build_shell_command(template: str, args: dict[str, str]) -> list[str]:
    if template not in SHELL_TEMPLATES:
        raise ValueError(f"shell template {template!r} is not in the whitelist")
    argv = []
    for part in SHELL_TEMPLATES[template]:
        if part.startswith("{") and part.endswith("}"):
            key = part[1:-1]
            if key not in args:
                raise KeyError(f"missing shell template arg: {key}")
            argv.append(str(args[key]))
        else:
            argv.append(part)
    return argv


class ShellExecutor:
    """Whitelisted, query-only shell templates. Goal must be JSON:
    {"template": name, "args": {...}} — anything else is rejected."""

    name = "shell"

    def __init__(self, exec_fn: Callable = _default_exec):
        self.exec_fn = exec_fn

    async def run(self, task: Task) -> str:
        try:
            spec = json.loads(task.goal)
            template, args = spec["template"], spec.get("args", {})
        except (json.JSONDecodeError, TypeError, KeyError) as exc:
            raise ValueError(
                "shell goal must be JSON {'template': ..., 'args': {...}}"
            ) from exc
        argv = build_shell_command(template, args)
        code, out, err = await self.exec_fn(argv, None)
        if code != 0:
            raise RuntimeError(f"shell template {template} exited {code}: {err.strip()}")
        return out


def make_executor(name: str, config: dict | None = None) -> Executor:
    config = config or {}
    if name == "claude_code":
        return ClaudeCodeExecutor(workdir=config.get("claude_code_workdir"))
    if name == "shell":
        return ShellExecutor()
    if name == "noop":
        return NoopExecutor()
    if name == "openclaw":
        from skills.openclaw.hook import OpenClawExecutor

        return OpenClawExecutor(config.get("openclaw_dir"))
    raise ValueError(f"unknown executor: {name!r}")
