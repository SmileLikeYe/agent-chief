"""Step 12 acceptance: 4× dismissed_fast on one topic measurably lowers its
future score; threshold bounds respected under extreme ratios; engaged/
dismissed sets maintained from signals."""

from datetime import UTC, datetime

import pytest

from core.learner import Learner, effective_threshold, tune_adjust
from core.schema import Decision, Event, SceneState
from core.scorer import SimilarityClassifier, score_and_route
from core.state import State
from judge.base import JudgeResult

NOW = datetime(2026, 7, 6, 14, 0, tzinfo=UTC)


def ev(topic="news.newsletter", summary="JS Weekly #712"):
    return Event(id="evt_x", source="t", topic=topic, summary=summary, received_at=NOW)


def decision(comps=None):
    return Decision(
        event_id="evt_x",
        route="interrupt",
        score=0.6,
        components=comps or {"urgency": 0.6, "relevance": 0.6, "actionability": 0.6,
                             "novelty": 0.6, "confidence": 0.6},
        scene="idle",
        scene_confidence=0.8,
        cost=0.0,
        reason="t",
        stage=3,
    )


def jr(v=0.6):
    return JudgeResult(urgency=v, relevance=v, actionability=v, novelty=v, confidence=v,
                       reason="t")


async def scored_with_learned_weights(state, topic="news.newsletter") -> float:
    learner = Learner(state)
    weights = await learner.topic_weights(topic)
    scene = SceneState(scene="idle", confidence=0.8, signals={}, at=NOW)
    _, score, _, _ = score_and_route(jr(), scene, topic_weights=weights)
    return score


async def test_dismissed_fast_x4_lowers_future_score(tmp_path):
    async with State.open(tmp_path / "s.db") as state:
        before = await scored_with_learned_weights(state)
        learner = Learner(state)
        for _ in range(4):
            await learner.record(ev(), decision(), "dismissed_fast", at=NOW)
        after = await scored_with_learned_weights(state)
        assert after < before - 0.1, f"expected a measurable drop, got {before} -> {after}"


async def test_acted_raises_future_score_on_high_dims(tmp_path):
    async with State.open(tmp_path / "s.db") as state:
        learner = Learner(state)
        comps = {"urgency": 0.9, "relevance": 0.9, "actionability": 0.9,
                 "novelty": 0.9, "confidence": 0.9}
        for _ in range(3):
            await learner.record(ev(), decision(comps), "acted", at=NOW)
        after = await scored_with_learned_weights(state)
        assert after > 0.6  # weights drifted toward the engaged profile


async def test_promote_bumps_urgency_weight_capped(tmp_path):
    async with State.open(tmp_path / "s.db") as state:
        learner = Learner(state)
        for _ in range(5):
            await learner.record(ev(), decision(), "promote", at=NOW)
        weights = await learner.topic_weights("news.newsletter")
        assert weights["urgency"] == pytest.approx(Learner.URGENCY_CAP)


async def test_signals_maintain_engaged_and_dismissed_sets(tmp_path):
    async with State.open(tmp_path / "s.db") as state:
        clf = SimilarityClassifier()
        learner = Learner(state, classifier=clf)
        await learner.record(ev(summary="CI failed on main branch today"), decision(), "acted",
                             at=NOW)
        await learner.record(ev(summary="LinkedIn: new connection requests"), decision(),
                             "dismissed_fast", at=NOW)
        assert clf.classify("CI failed on main branch today").action == "route"
        assert clf.classify("LinkedIn: new connection requests").action == "drop"


async def test_task_signals_adjust_dispatch_propensity(tmp_path):
    async with State.open(tmp_path / "s.db") as state:
        learner = Learner(state)
        base = await learner.dispatch_propensity("claude_code", "dev.ci")
        await learner.record(ev(topic="dev.ci"), decision(), "task_ok", at=NOW,
                             executor="claude_code")
        up = await learner.dispatch_propensity("claude_code", "dev.ci")
        await learner.record(ev(topic="dev.ci"), decision(), "task_fail", at=NOW,
                             executor="claude_code")
        await learner.record(ev(topic="dev.ci"), decision(), "task_fail", at=NOW,
                             executor="claude_code")
        down = await learner.dispatch_propensity("claude_code", "dev.ci")
        assert up > base > down or (up > base and down < up)


async def test_feedback_rows_persisted(tmp_path):
    async with State.open(tmp_path / "s.db") as state:
        learner = Learner(state)
        await learner.record(ev(), decision(), "acted", at=NOW)
        rows = await state.feedback_rows()
        assert rows[0]["signal"] == "acted"


# --- global threshold tuning (SPEC §4.6) ---


def test_tune_adjust_directions():
    assert tune_adjust(0.0, dismissed_fast_ratio=0.5) == pytest.approx(0.02)
    assert tune_adjust(0.0, dismissed_fast_ratio=0.1) == pytest.approx(-0.01)
    assert tune_adjust(0.0, dismissed_fast_ratio=0.25) == 0.0  # dead zone


def test_threshold_bounds_respected_under_extreme_ratios():
    adjust = 0.0
    for _ in range(100):  # 100 days of 100% dismissals
        adjust = tune_adjust(adjust, dismissed_fast_ratio=1.0)
    assert effective_threshold("idle", adjust) <= 0.95
    adjust = 0.0
    for _ in range(200):  # 200 days of perfect tact
        adjust = tune_adjust(adjust, dismissed_fast_ratio=0.0)
    assert effective_threshold("sleeping", adjust) >= 0.35
    assert effective_threshold("idle", adjust) >= 0.35


async def test_rebuild_classifier_from_persisted_history(tmp_path):
    """review(phase2): stage-2 sets must survive a restart via feedback history."""
    async with State.open(tmp_path / "s.db") as state:
        event = ev(topic="dev.ci", summary="CI failed on main branch today")
        await state.save_event(event)
        await state.save_decision(decision())
        learner = Learner(state)
        await learner.record(event, decision(), "acted", at=NOW)

        fresh = SimilarityClassifier()
        restarted = Learner(state, classifier=fresh)
        await restarted.rebuild_classifier()
        assert fresh.classify("CI failed on main branch today").action == "route"


async def test_daily_threshold_tuning_persists_adjust(tmp_path):
    """review(phase4): §4.6 tuning must actually run and feed routing."""
    from core.learner import daily_threshold_tuning, load_threshold_adjust

    async with State.open(tmp_path / "s.db") as state:
        # 10 interrupts, 6 dismissed fast (60% > 40%) → +0.02
        for i in range(10):
            d = decision()
            await state.save_decision(d.model_copy(update={"event_id": f"evt_{i}"}))
        for i in range(6):
            await state.save_feedback(f"evt_{i}", "dismissed_fast", NOW)
        adjust = await daily_threshold_tuning(state, now=NOW)
        assert adjust == pytest.approx(0.02)
        assert await load_threshold_adjust(state) == pytest.approx(0.02)


def test_threshold_adjust_changes_routing():
    from core.scorer import score_and_route

    scene = SceneState(scene="idle", confidence=0.8, signals={}, at=NOW)
    r = jr(0.5)  # score 0.5 vs idle threshold 0.45
    route_before, *_ = score_and_route(r, scene)
    route_after, *_ = score_and_route(r, scene, threshold_adjust=0.10)  # threshold 0.55
    assert route_before == "interrupt" and route_after == "digest"
