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


# --- pin lifecycle (v3): explicit un-pinning + staleness decay ---


async def test_should_not_interrupt_removes_a_pin_immediately(tmp_path):
    """A pin forces an interrupt on every event of its topic; when the user says
    'stop flagging this' outright, one signal is enough to drop it — no need to
    saturate, unlike creation."""
    async with State.open(tmp_path / "s.db") as state:
        learner = Learner(state)
        await state.add_pin("dev.ci", NOW)
        assert await state.is_pinned("dev.ci")

        event = _event("dev.ci")
        await learner.record(event, _decision(0.3), "should_not_interrupt", at=NOW)
        assert not await state.is_pinned("dev.ci")  # gone after a single correction


async def test_unpin_only_from_explicit_signal_not_from_a_fast_dismissal(tmp_path):
    """A soft 'dismissed_fast' decays weights but must NOT tear down a hard pin —
    only the explicit should_not_interrupt does."""
    async with State.open(tmp_path / "s.db") as state:
        learner = Learner(state)
        await state.add_pin("dev.ci", NOW)
        event = _event("dev.ci")
        for r in range(5):
            await learner.record(event, _decision(0.3), "dismissed_fast",
                                 at=NOW + timedelta(minutes=r))
        assert await state.is_pinned("dev.ci")  # survives soft dismissals


async def test_a_firing_pin_refreshes_its_freshness_clock(tmp_path):
    from tests.helpers import make_brain

    async with State.open(tmp_path / "s.db") as state:
        brain = make_brain(state, tmp_path)
        await state.add_pin("dev.ci", NOW)
        later = NOW + timedelta(days=20)
        brain.now_fn = lambda: later
        await brain.process({"source": "ci", "topic": "dev.ci", "summary": "done"})
        pins = await state.learned_pins()
        assert pins["dev.ci"]["last_fired"] == later.isoformat()  # touched, not stale


async def test_nightly_prune_drops_stale_pins_but_keeps_fresh_ones(tmp_path):
    from core.learner import PIN_STALE_DAYS, prune_stale_pins

    async with State.open(tmp_path / "s.db") as state:
        await state.add_pin("stale.topic", NOW)
        await state.add_pin("fresh.topic", NOW)
        # fresh.topic fired yesterday; stale.topic hasn't fired since NOW
        now = NOW + timedelta(days=PIN_STALE_DAYS + 1)
        await state.touch_pin("fresh.topic", now - timedelta(days=1))

        dropped = await prune_stale_pins(state, now=now)
        assert dropped == ["stale.topic"]
        assert not await state.is_pinned("stale.topic")
        assert await state.is_pinned("fresh.topic")


async def test_legacy_string_pins_are_readable_and_prunable(tmp_path):
    """A pin written by v2 (a bare ISO string) must still be honoured, touched,
    and pruned after the upgrade — never silently lost."""
    async with State.open(tmp_path / "s.db") as state:
        await state.set_meta(State._PINS_KEY, {"old.topic": NOW.isoformat()})
        assert await state.is_pinned("old.topic")

        now = NOW + timedelta(days=100)
        dropped = await state.prune_stale_pins(now=now, max_idle_days=30)
        assert dropped == ["old.topic"]  # legacy last_fired == pinned_at, so stale
