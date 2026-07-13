"""Learned interrupt pins (SPEC §4.6, cohort-v2): when EMA weights saturate but
the user keeps correcting a topic to should-interrupt, the learner escalates to a
hard per-topic pin, and the brain honours it like a stage-1 rule."""

from datetime import UTC, datetime, timedelta

from core.learner import Learner
from core.schema import Decision, Event
from core.state import State

NOW = datetime(2026, 7, 6, 14, 0, tzinfo=UTC)


def _event(topic="oncall.page"):
    return Event(id="evt_p", source="agent", topic=topic, summary="quiet but wanted",
                 received_at=NOW)


def _decision(strength: float) -> Decision:
    comps = {d: strength for d in
             ("urgency", "relevance", "actionability", "novelty", "confidence")}
    return Decision(event_id="evt_p", route="digest", score=strength, components=comps,
                    scene="meeting", scene_confidence=0.8, cost=0.0, reason="t", stage=3)


async def test_learner_escalates_to_a_pin_only_after_ema_saturates(tmp_path):
    async with State.open(tmp_path / "s.db") as state:
        learner = Learner(state)
        event, decision = _event(), _decision(0.38)  # a quiet, unreachable topic

        await learner.record(event, decision, "should_interrupt", at=NOW)
        assert not await state.is_pinned(event.topic)  # one nudge never pins

        # keep correcting; the weight step shrinks each round until EMA saturates
        for r in range(1, 12):
            await learner.record(event, decision, "should_interrupt",
                                 at=NOW + timedelta(minutes=r))
            if await state.is_pinned(event.topic):
                break
        assert await state.is_pinned(event.topic)  # escalated to a hard pin
        assert event.topic in await state.learned_pins()


async def test_a_pin_only_fires_on_should_interrupt_not_on_dismissals(tmp_path):
    """The escalation is one-directional: pins are created only from repeated
    should-interrupt, never from a saturating dismissal — so an unwanted topic
    (which only ever draws should_not_interrupt) can never be pinned."""
    async with State.open(tmp_path / "s.db") as state:
        learner = Learner(state)
        event, decision = _event("news.spam"), _decision(0.05)
        for r in range(12):
            await learner.record(event, decision, "should_not_interrupt",
                                 at=NOW + timedelta(minutes=r))
        assert not await state.is_pinned(event.topic)


async def test_brain_routes_a_pinned_topic_to_interrupt(tmp_path):
    from ingest.http import create_app  # noqa: F401  (ensures app import path is sane)
    from tests.helpers import make_brain

    async with State.open(tmp_path / "s.db") as state:
        brain = make_brain(state, tmp_path)
        await state.add_pin("dev.ci", NOW)
        decision = await brain.process(
            {"source": "ci", "topic": "dev.ci", "summary": "pipeline finished"}
        )
        assert decision.route == "interrupt"
        assert decision.matched_rules == ["pin"]
        assert decision.stage == 1  # a pin fires cheaply, before the judge
