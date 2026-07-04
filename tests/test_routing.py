"""Step 5 acceptance: routing unit tests for all five routes; memory-hit
relevance boost verified with a mocked hit."""

from datetime import UTC, datetime

import pytest

from core.schema import SceneState
from core.scorer import score_and_route
from judge.base import JudgeResult
from judge.fixtures import FixtureJudge

NOW = datetime(2026, 7, 6, 14, 0, tzinfo=UTC)


def scene(name="idle", conf=0.8) -> SceneState:
    return SceneState(scene=name, confidence=conf, signals={}, at=NOW)


def jr(**kw) -> JudgeResult:
    defaults = dict(
        urgency=0.5,
        relevance=0.5,
        actionability=0.5,
        novelty=0.5,
        confidence=0.5,
        dispatchable=False,
        dispatch_goal=None,
        memorize=None,
        reason="test",
    )
    defaults.update(kw)
    return JudgeResult(**defaults)


# --- the five routes ---


def test_route_interrupt():
    # equal weights 0.2 → score = mean(dims) = 0.9 ≥ idle threshold 0.45
    r = jr(urgency=0.9, relevance=0.9, actionability=0.9, novelty=0.9, confidence=0.9)
    route, score, _, _ = score_and_route(r, scene("idle"))
    assert route == "interrupt" and score == pytest.approx(0.9)


def test_route_digest():
    # score 0.42: above 0.40 floor, below idle threshold 0.45
    r = jr(urgency=0.42, relevance=0.42, actionability=0.42, novelty=0.42, confidence=0.42)
    route, _, _, _ = score_and_route(r, scene("idle"))
    assert route == "digest"


def test_route_drop():
    r = jr(urgency=0.1, relevance=0.1, actionability=0.1, novelty=0.1, confidence=0.1)
    route, _, _, _ = score_and_route(r, scene("idle"))
    assert route == "drop"


def test_route_curate():
    r = jr(
        urgency=0.1,
        relevance=0.1,
        actionability=0.1,
        novelty=0.1,
        confidence=0.1,
        memorize="user wants to watch XX's next SDK release",
    )
    route, _, _, _ = score_and_route(r, scene("idle"))
    assert route == "curate"


def test_route_dispatch_from_interrupt():
    r = jr(
        urgency=0.9,
        relevance=0.9,
        actionability=0.9,
        novelty=0.9,
        confidence=0.9,
        dispatchable=True,
        dispatch_goal="fix CI on main",
    )
    route, _, _, _ = score_and_route(r, scene("idle"))
    assert route == "dispatch"


def test_route_dispatch_from_digest():
    r = jr(
        urgency=0.42,
        relevance=0.42,
        actionability=0.42,
        novelty=0.42,
        confidence=0.42,
        dispatchable=True,
        dispatch_goal="summarize release notes",
    )
    route, _, _, _ = score_and_route(r, scene("idle"))
    assert route == "dispatch"


def test_dispatchable_dropped_event_stays_dropped():
    r = jr(
        urgency=0.1,
        relevance=0.1,
        actionability=0.1,
        novelty=0.1,
        confidence=0.1,
        dispatchable=True,
    )
    route, _, _, _ = score_and_route(r, scene("idle"))
    assert route == "drop"


# --- scene interplay ---


def test_scene_threshold_gates_interrupt():
    # 0.9 clears idle (0.45) but not sleeping (0.95)
    r = jr(urgency=0.9, relevance=0.9, actionability=0.9, novelty=0.9, confidence=0.9)
    route, _, _, _ = score_and_route(r, scene("sleeping", conf=0.9))
    assert route == "digest"


def test_low_scene_confidence_downgrades_interrupt():
    r = jr(urgency=0.9, relevance=0.9, actionability=0.9, novelty=0.9, confidence=0.9)
    route, _, _, _ = score_and_route(r, scene("idle", conf=0.5))
    assert route == "digest"


def test_threshold_override_from_policy():
    r = jr(urgency=0.5, relevance=0.5, actionability=0.5, novelty=0.5, confidence=0.5)
    route, _, _, _ = score_and_route(r, scene("deep_work"), threshold_overrides={"deep_work": 0.4})
    assert route == "interrupt"


# --- memory-hit relevance boost (SPEC §4.4) ---


def test_memory_hit_boosts_relevance_1_2x():
    r = jr(relevance=0.6)
    _, _, comps, _ = score_and_route(r, scene("idle"), memory_hit=True)
    assert comps["relevance"] == pytest.approx(0.72)


def test_memory_hit_relevance_capped_at_1():
    r = jr(relevance=0.95)
    _, _, comps, _ = score_and_route(r, scene("idle"), memory_hit=True)
    assert comps["relevance"] == 1.0


def test_memory_hit_can_flip_digest_to_interrupt():
    r = jr(urgency=0.44, relevance=0.44, actionability=0.44, novelty=0.44, confidence=0.44)
    route_no_hit, _, _, _ = score_and_route(r, scene("idle"))
    route_hit, _, _, _ = score_and_route(r, scene("idle"), memory_hit=True)
    assert route_no_hit == "digest" and route_hit == "interrupt"


# --- fixture judge ---


async def test_fixture_judge_returns_recorded_result():
    judge = FixtureJudge(
        {
            "evt_1": dict(
                urgency=0.9,
                relevance=0.8,
                actionability=0.7,
                novelty=0.6,
                confidence=0.9,
                dispatchable=True,
                dispatch_goal="fix it",
                memorize=None,
                reason="recorded",
            )
        }
    )

    class Ev:
        id = "evt_1"

    result = await judge.judge(Ev(), None)
    assert result.urgency == 0.9 and result.dispatch_goal == "fix it"


async def test_fixture_judge_unknown_event_raises():
    judge = FixtureJudge({})

    class Ev:
        id = "evt_missing"

    with pytest.raises(LookupError):
        await judge.judge(Ev(), None)
