"""Step 28 acceptance (SPEC v3.1): failure injection + graceful degradation.

- judge returns malformed JSON / times out / backend fully down → no crash;
- degraded decisions are conservative: borderline → digest, NEVER interrupt;
- decisions carry degraded=true in the audit log;
- auto-recovery when the backend returns; `chief status` shows the state.
"""

import asyncio
import json

import httpx
from typer.testing import CliRunner

from core.brain import load_degraded
from core.state import AuditLog, State
from judge.base import JudgeResult
from judge.deepseek import DeepSeekJudge
from tests.helpers import StaticJudge, make_brain

URGENT = {
    "source": "pager",
    "topic": "infra.alerts",
    "summary": "Primary database is on fire, error rate 100%",
    "claimed_urgency": "high",
}


def down_judge():
    """Backend fully down: every request raises a connect error."""

    def handler(request):
        raise httpx.ConnectError("connection refused", request=request)

    return DeepSeekJudge(model="deepseek-chat", api_key="k",
                         transport=httpx.MockTransport(handler))


def garbage_judge():
    """Backend up but returns non-JSON garbage every time."""
    body = {"choices": [{"message": {"content": "sorry, as an AI I cannot"}}], "usage": {}}
    return DeepSeekJudge(model="deepseek-chat", api_key="k",
                         transport=httpx.MockTransport(lambda r: httpx.Response(200, json=body)))


class HangingJudge:
    name = "hanging"

    async def judge(self, event, context):
        await asyncio.sleep(60)


class FlakyJudge:
    """Fails on the first call, healthy afterwards."""

    name = "flaky"

    def __init__(self):
        self.calls = 0

    async def judge(self, event, context):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("boom")
        return JudgeResult(urgency=0.5, relevance=0.5, actionability=0.5,
                           novelty=0.5, confidence=0.5, reason="healthy again")


async def test_backend_down_degrades_to_digest_not_interrupt(tmp_path):
    async with State.open(tmp_path / "s.db") as state:
        brain = make_brain(state, tmp_path, judge=down_judge())
        decision = await brain.process(dict(URGENT))
        assert decision.route == "digest"  # never interrupt while blind
        assert decision.degraded is True
        assert "conservative" in decision.reason


async def test_malformed_json_after_retries_degrades(tmp_path):
    async with State.open(tmp_path / "s.db") as state:
        brain = make_brain(state, tmp_path, judge=garbage_judge())
        decision = await brain.process(dict(URGENT))
        assert decision.route == "digest" and decision.degraded


async def test_judge_timeout_degrades(tmp_path):
    async with State.open(tmp_path / "s.db") as state:
        brain = make_brain(state, tmp_path, judge=HangingJudge(), judge_timeout=0.05)
        decision = await brain.process(dict(URGENT))
        assert decision.route == "digest" and decision.degraded


async def test_stage1_rules_still_fire_while_degraded(tmp_path):
    async with State.open(tmp_path / "s.db") as state:
        brain = make_brain(state, tmp_path, judge=down_judge())
        decision = await brain.process(
            {"source": "hb", "topic": "ops.heartbeat",
             "summary": "Heartbeat: all clear, nothing to report"}
        )
        assert decision.route == "drop"  # rules-only routing is intact
        assert decision.degraded is False  # the rules saw it, not the judge


async def test_degraded_flag_lands_in_audit_log(tmp_path):
    audit_path = tmp_path / "audit.jsonl"
    async with State.open(tmp_path / "s.db") as state:
        brain = make_brain(state, tmp_path, judge=down_judge(), audit=AuditLog(audit_path))
        await brain.process(dict(URGENT))
    line = json.loads(audit_path.read_text(encoding="utf-8").splitlines()[-1])
    assert line["degraded"] is True


async def test_degradation_state_persists_and_recovers(tmp_path):
    async with State.open(tmp_path / "s.db") as state:
        flaky = FlakyJudge()
        brain = make_brain(state, tmp_path, judge=flaky)

        first = await brain.process(dict(URGENT))
        assert first.degraded is True
        info = await load_degraded(state)
        assert info and "boom" in info["last_error"]

        second = await brain.process({**URGENT, "summary": "Replica lag spiking",
                                      "dedup_key": "second"})
        assert second.degraded is False  # auto-recovered on the next success
        assert await load_degraded(state) is None


def test_cli_status_shows_degradation_state(tmp_path, monkeypatch):
    monkeypatch.setenv("CHIEF_HOME", str(tmp_path))
    from cli.main import app
    from core.config import db_path

    async def seed():
        async with State.open(db_path()) as state:
            brain = make_brain(state, tmp_path, judge=down_judge())
            await brain.process(dict(URGENT))

    asyncio.run(seed())
    result = CliRunner().invoke(app, ["status"])
    assert result.exit_code == 0, result.output
    assert "degraded" in result.output.lower()


def test_cli_status_healthy_when_not_degraded(tmp_path, monkeypatch):
    monkeypatch.setenv("CHIEF_HOME", str(tmp_path))
    from cli.main import app
    from core.config import db_path

    async def seed():
        async with State.open(db_path()) as state:
            brain = make_brain(state, tmp_path, judge=StaticJudge())
            await brain.process(dict(URGENT))

    asyncio.run(seed())
    result = CliRunner().invoke(app, ["status"])
    assert result.exit_code == 0, result.output
    assert "degraded" not in result.output.lower()


async def test_degradation_marker_is_isolated_from_topic_weights(tmp_path):
    """The meta-table marker must be invisible to (and unclobberable via) the
    topic-weights namespace that events and the learner write into."""
    async with State.open(tmp_path / "s.db") as state:
        brain = make_brain(state, tmp_path, judge=down_judge())
        await brain.process(dict(URGENT))
        assert await load_degraded(state)  # marker set in meta

        # a hostile writer hammering the old key's namespace changes nothing
        await state.set_topic_weights("__degraded__", {"active": False})
        await state.set_topic_weights("degraded", {"active": False})
        assert await load_degraded(state)  # still degraded

        # and the marker never leaks back as scoring weights for any topic
        assert await state.get_topic_weights("degraded") == {"active": False}
        assert (await state.get_meta("degraded"))["active"] is True
