"""Step 22 acceptance: skill lint passes (structure checks); executor and
delivery callback exercised against a faked local OpenClaw directory."""

import json
from pathlib import Path

from core.schema import Task
from delivery.base import DeliveryMessage
from skills.openclaw.hook import OpenClawChannel, OpenClawExecutor

SKILL = Path(__file__).parent.parent / "skills" / "openclaw" / "SKILL.md"


# --- skill lint ---


def test_skill_md_exists_with_frontmatter():
    text = SKILL.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    fm = text.split("---")[1]
    assert "name:" in fm and "description:" in fm


def test_skill_md_core_contract():
    text = SKILL.read_text(encoding="utf-8").lower()
    assert "must not" in text  # never message the user directly
    assert "propose" in text  # call chief's MCP propose
    assert "obey" in text  # and obey the returned decision


# --- task injection (executor=openclaw, SPEC §4.5) ---


async def test_executor_writes_task_into_inject_dir(tmp_path):
    ex = OpenClawExecutor(openclaw_dir=str(tmp_path))
    task = Task(
        id="task_1",
        origin_event_id="evt_x",
        goal="find rebooking options",
        executor="openclaw",
        acceptance="3 options listed",
    )
    result = await ex.run(task)
    files = list((tmp_path / "tasks").glob("*.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text())
    assert data["goal"] == "find rebooking options"
    assert data["origin"] == "chief"
    assert "task_1" in result


# --- delivery callback riding OpenClaw channels (SPEC §4.9) ---


async def test_channel_writes_outbox_message(tmp_path):
    ch = OpenClawChannel(openclaw_dir=str(tmp_path))
    assert ch.max_level == "ring"
    msg = DeliveryMessage(
        summary="Flight delayed", event_id="evt_x", topic="travel", plan="3 options"
    )
    await ch.send(msg, level="silent")
    files = list((tmp_path / "outbox").glob("*.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text())
    assert data["silent"] is True
    assert "Flight delayed" in data["text"]
