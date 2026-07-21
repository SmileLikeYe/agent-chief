"""Step 44 acceptance: the generic inbound push pipe.

The contract: `source` + `summary` is enough; a full round-trip through the real
webhook app returns a valid Decision; a bad token is rejected; the one-line
render names the route. This is `chief push` and the Telegram relay's shared
core (SPEC §4.1, generalized).
"""

import httpx
import pytest

from core.schema import Decision
from ingest.push import describe_decision, push_payload, push_to_daemon

# --- the envelope ---


def test_push_payload_minimal_is_just_source_and_summary():
    p = push_payload("CI failed on main")
    assert p == {"source": "push", "summary": "CI failed on main"}
    assert "topic" not in p  # left to inference


def test_push_payload_drops_absent_optionals_and_carries_present_ones():
    p = push_payload(
        "deploy done", source="ci", topic="dev.ci",
        claimed_urgency="high", suggested_action="check the dashboard",
    )
    assert p["source"] == "ci" and p["topic"] == "dev.ci"
    assert p["claimed_urgency"] == "high" and p["suggested_action"] == "check the dashboard"
    assert "detail" not in p


def test_push_payload_clamps_an_over_long_summary():
    p = push_payload("x" * 500)
    assert len(p["summary"]) == 200  # would 422 against Event.summary otherwise


# --- the one-line render ---


def test_describe_decision_names_route_scene_and_reason():
    d = Decision(
        event_id="evt_x", route="interrupt", score=4.2, scene="deep_work",
        scene_confidence=1.0, cost=0.0, reason="production incident", stage=1,
    )
    line = describe_decision(d)
    assert "interrupt" in line and "deep_work" in line
    assert "4.2" in line and "production incident" in line


def test_describe_decision_handles_a_scoreless_decision():
    d = Decision(
        event_id="evt_y", route="drop", score=None, scene="idle",
        scene_confidence=1.0, cost=0.0, reason="deduped", stage=0,
    )
    assert "no score" in describe_decision(d)


# --- the client half of `chief push` against the real app ---


@pytest.fixture
async def app_transport(tmp_path):
    from core.state import State
    from ingest.http import create_app
    from tests.helpers import make_brain

    async with State.open(tmp_path / "s.db") as state:
        app = create_app(make_brain(state, tmp_path), token="sekrit")
        yield httpx.ASGITransport(app=app)


async def test_push_to_daemon_round_trips_a_decision(app_transport):
    decision = await push_to_daemon(
        push_payload("something happened", source="script"),
        token="sekrit", transport=app_transport,
    )
    assert isinstance(decision, Decision)
    assert decision.route in ("interrupt", "digest", "dispatch", "curate", "drop")
    assert decision.reason


async def test_push_to_daemon_rejects_a_bad_token(app_transport):
    with pytest.raises(httpx.HTTPStatusError) as exc:
        await push_to_daemon(
            push_payload("probe"), token="wrong", transport=app_transport
        )
    assert exc.value.response.status_code == 401


async def test_push_from_anywhere_flows_through_the_real_funnel(app_transport):
    """The full point: a push isn't a mock echo — it runs the same pipeline every
    source does. Proven by persistence: an identical second push dedups to drop,
    which only happens if the first one was scored and stored."""
    payload = push_payload("checkout 500s spiking", source="pager", topic="dev.incident")
    first = await push_to_daemon(payload, token="sekrit", transport=app_transport)
    second = await push_to_daemon(payload, token="sekrit", transport=app_transport)
    assert first.route != "drop"
    assert second.route == "drop" and "dedup" in second.matched_rules
