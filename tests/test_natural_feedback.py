"""Step 32 acceptance (SPEC v3.2): natural feedback — "should/shouldn't have
interrupted me" as first-class signals, stronger than passive ones, reachable
from HTTP, MCP, and Telegram buttons."""

from datetime import UTC, datetime

import httpx
import pytest

from core.learner import SIGNAL_EFFECTS, Learner
from core.schema import Decision, Event
from core.scorer import score_and_route
from core.state import State
from judge.base import JudgeResult
from tests.helpers import StaticJudge, make_brain

NOW = datetime(2026, 7, 6, 14, 0, tzinfo=UTC)


def make_event(topic="dev.ci"):
    return Event(id="evt_nf", source="t", topic=topic,
                 summary="CI failed on main", received_at=NOW)


def make_decision(route="digest"):
    return Decision(event_id="evt_nf", route=route, score=0.5,
                    components={d: 0.75 for d in
                                ("urgency", "relevance", "actionability",
                                 "novelty", "confidence")},
                    scene="idle", scene_confidence=0.8, cost=0.0,
                    reason="t", stage=3)


def scene():
    from core.schema import SceneState
    return SceneState(scene="idle", confidence=0.8, signals={}, at=NOW)


def judged(score=0.5):
    return JudgeResult(urgency=score, relevance=score, actionability=score,
                       novelty=score, confidence=score, reason="t")


# --- signal strength & direction -------------------------------------------------


def test_natural_signals_are_stronger_than_passive_ones():
    assert SIGNAL_EFFECTS["should_interrupt"][0] > SIGNAL_EFFECTS["acted"][0]
    assert SIGNAL_EFFECTS["should_not_interrupt"][0] > SIGNAL_EFFECTS["dismissed_fast"][0]
    assert SIGNAL_EFFECTS["should_interrupt"][1] == +1
    assert SIGNAL_EFFECTS["should_not_interrupt"][1] == -1


async def test_signal_directions_move_scores(tmp_path):
    async with State.open(tmp_path / "s.db") as state:
        learner = Learner(state)

        def score(weights):
            return score_and_route(judged(), scene(), topic_weights=weights)[1]

        baseline = score(await state.get_topic_weights("dev.ci"))
        for _ in range(3):
            await learner.record(make_event(), make_decision(), "should_interrupt", at=NOW)
        boosted = score(await state.get_topic_weights("dev.ci"))
        assert boosted > baseline

        for _ in range(6):
            await learner.record(make_event(), make_decision(), "should_not_interrupt", at=NOW)
        demoted = score(await state.get_topic_weights("dev.ci"))
        assert demoted < boosted


# --- HTTP path ---------------------------------------------------------------------


@pytest.fixture
async def client_with_learner(tmp_path):
    from ingest.http import create_app

    async with State.open(tmp_path / "s.db") as state:
        brain = make_brain(state, tmp_path, judge=StaticJudge())
        learner = Learner(state)
        app = create_app(brain, token="sekrit", learner=learner)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            yield c, brain, state


async def test_http_feedback_endpoint_learns(client_with_learner):
    c, brain, state = client_with_learner
    decision = await brain.process(
        {"source": "ci", "topic": "dev.ci", "summary": "CI failed on main"})
    resp = await c.post("/v1/feedback",
                        headers={"Authorization": "Bearer sekrit"},
                        json={"event_id": decision.event_id,
                              "signal": "should_not_interrupt"})
    assert resp.status_code == 200
    assert resp.json()["learned"] is True
    assert await state.count_feedback(signal="should_not_interrupt") == 1


async def test_http_feedback_rejects_bad_token_and_bad_signal(client_with_learner):
    c, brain, _ = client_with_learner
    resp = await c.post("/v1/feedback", json={"event_id": "x", "signal": "acted"})
    assert resp.status_code == 401
    resp = await c.post("/v1/feedback",
                        headers={"Authorization": "Bearer sekrit"},
                        json={"event_id": "x", "signal": "rm -rf"})
    assert resp.status_code == 422


async def test_http_feedback_unknown_event_still_records(client_with_learner):
    # feedback may outlive local event retention; store it, learn nothing
    c, _, state = client_with_learner
    resp = await c.post("/v1/feedback",
                        headers={"Authorization": "Bearer sekrit"},
                        json={"event_id": "evt_gone", "signal": "should_interrupt"})
    assert resp.status_code == 200
    assert resp.json()["learned"] is False
    assert await state.count_feedback(signal="should_interrupt") == 1


# --- Telegram buttons -----------------------------------------------------------------


def test_telegram_buttons_include_natural_feedback():
    from delivery.telegram import BUTTONS

    signals = [s for _, s in BUTTONS]
    assert "should_interrupt" in signals
    assert "should_not_interrupt" in signals
    assert signals.index("should_interrupt") > signals.index("muted") - 4  # sanity
