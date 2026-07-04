"""Implements SPEC §4.9: OpenClaw integration — task injection (executor) and
the delivery callback that lets interrupts ride OpenClaw's existing channels.

Both sides speak plain JSON files under the OpenClaw home directory
(`~/.openclaw` by default): `tasks/` is the task-injection inbox, `outbox/`
is picked up by OpenClaw's channel workers.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

from core.schema import Task
from delivery.base import DeliveryMessage, render_message

DEFAULT_DIR = "~/.openclaw"


class OpenClawExecutor:
    """executor=openclaw: write the task into OpenClaw's injection inbox."""

    name = "openclaw"

    def __init__(self, openclaw_dir: str | None = None):
        self.home = Path(openclaw_dir or DEFAULT_DIR).expanduser()

    async def run(self, task: Task) -> str:
        inbox = self.home / "tasks"
        inbox.mkdir(parents=True, exist_ok=True)
        path = inbox / f"{task.id}.json"
        path.write_text(
            json.dumps(
                {
                    "origin": "chief",
                    "task_id": task.id,
                    "goal": task.goal,
                    "acceptance": task.acceptance,
                    "injected_at": datetime.now(UTC).isoformat(),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return f"injected {task.id} into OpenClaw at {path}"


class OpenClawChannel:
    """Delivery callback: chief's interrupts ride OpenClaw's channels."""

    name = "openclaw"
    max_level = "ring"

    def __init__(self, openclaw_dir: str | None = None):
        self.home = Path(openclaw_dir or DEFAULT_DIR).expanduser()

    async def send(self, msg: DeliveryMessage, level: str) -> None:
        outbox = self.home / "outbox"
        outbox.mkdir(parents=True, exist_ok=True)
        stamp = f"{datetime.now(UTC):%Y%m%d%H%M%S%f}"
        (outbox / f"chief_{msg.event_id}_{stamp}.json").write_text(
            json.dumps(
                {
                    "origin": "chief",
                    "event_id": msg.event_id,
                    "topic": msg.topic,
                    "text": render_message(msg),
                    "silent": level in ("terminal", "desktop", "silent", "vibrate"),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
