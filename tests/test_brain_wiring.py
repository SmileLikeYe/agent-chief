"""review(phase3): Brain must create Tasks for dispatch routes, act on
decisions (deliver/dispatch), and fold near-duplicates via triage merge."""

import asyncio
from datetime import UTC, datetime

from core.embedding import HashEmbedder
from core.state import State
from tests.helpers import StaticJudge, make_brain

NOW = datetime(2026, 7, 6, 14, 0, tzinfo=UTC)

PAYLOAD = {
    "source": "github-actions",
    "topic": "dev.ci",
    "summary": "CI failed on main: test_auth_flow broken by PR #482",
    "claimed_urgency": "high",
}


def dispatch_judge():
    return StaticJudge(
        urgency=0.9, relevance=0.9, actionability=0.9, novelty=0.9, confidence=0.9,
        dispatchable=True, dispatch_goal="fix the failing test on main",
    )


async def test_dispatch_route_creates_pending_task(tmp_path):
    async with State.open(tmp_path / "s.db") as state:
        brain = make_brain(state, tmp_path, judge=dispatch_judge())
        decision = await brain.process(dict(PAYLOAD))
        assert decision.route == "dispatch"
        assert decision.dispatch_task_id
        task = await state.load_task(decision.dispatch_task_id)
        assert task.status == "pending"
        assert task.goal == "fix the failing test on main"
        assert task.executor == "claude_code"


async def test_actor_hook_fires_on_decision(tmp_path):
    async with State.open(tmp_path / "s.db") as state:
        acted = []

        async def actor(event, decision):
            acted.append((event.id, decision.route))

        brain = make_brain(state, tmp_path, judge=dispatch_judge())
        brain.actor = actor
        decision = await brain.process(dict(PAYLOAD))
        await asyncio.sleep(0)  # let the fire-and-forget actor run
        assert acted == [(decision.event_id, "dispatch")]


async def test_actor_errors_never_break_processing(tmp_path):
    async with State.open(tmp_path / "s.db") as state:
        async def actor(event, decision):
            raise RuntimeError("channel down")

        brain = make_brain(state, tmp_path)
        brain.actor = actor
        decision = await brain.process(dict(PAYLOAD))
        await asyncio.sleep(0)
        assert decision.route  # processing survived


async def test_triage_merge_folds_near_duplicate(tmp_path):
    async with State.open(tmp_path / "s.db") as state:
        brain = make_brain(state, tmp_path, embedder=HashEmbedder())
        first = await brain.process(dict(PAYLOAD))
        assert first.route != "drop"

        near_dup = dict(PAYLOAD)
        near_dup["summary"] = PAYLOAD["summary"] + " (retry)"
        second = await brain.process(near_dup)
        assert second.event_id == first.event_id  # folded into the earlier event
        assert "merged near-duplicate" in second.reason

        merged = await state.load_event(first.event_id)
        assert "(retry)" in merged.summary
