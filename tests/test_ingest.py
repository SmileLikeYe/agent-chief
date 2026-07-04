"""Step 18 acceptance: webhook round-trip returns a valid Decision; MCP tools
exercised via client test; missing-topic event gets an inferred topic."""

import httpx
import pytest

from core.schema import Decision
from ingest.normalize import TopicInferrer, normalize

PAYLOAD = {
    "source": "flight-watcher",
    "topic": "travel.flight_change",
    "summary": "Flight CA1857 delayed 2.5h tonight",
    "claimed_urgency": "high",
}


# --- normalization (SPEC §4.1) ---


async def test_normalize_generates_id_and_dedup_key():
    ev = await normalize(dict(PAYLOAD))
    assert ev.id.startswith("evt_")
    assert ev.dedup_key  # hash of summary when absent
    assert ev.received_at is not None


async def test_normalize_is_dedup_stable():
    a = await normalize(dict(PAYLOAD))
    b = await normalize(dict(PAYLOAD))
    assert a.dedup_key == b.dedup_key
    assert a.id != b.id


async def test_missing_topic_gets_inferred():
    async def fake_llm(prompt: str) -> str:
        assert "delayed" in prompt
        return "travel.flight_change"

    inferrer = TopicInferrer(ask=fake_llm)
    payload = {k: v for k, v in PAYLOAD.items() if k != "topic"}
    ev = await normalize(payload, inferrer=inferrer)
    assert ev.topic == "travel.flight_change"


async def test_topic_inference_cached():
    calls = []

    async def fake_llm(prompt: str) -> str:
        calls.append(1)
        return "dev.ci"

    inferrer = TopicInferrer(ask=fake_llm)
    payload = {k: v for k, v in PAYLOAD.items() if k != "topic"}
    await normalize(dict(payload), inferrer=inferrer)
    await normalize(dict(payload), inferrer=inferrer)
    assert len(calls) == 1


async def test_topic_inference_heuristic_without_llm():
    payload = {k: v for k, v in PAYLOAD.items() if k != "topic"}
    ev = await normalize(payload, inferrer=TopicInferrer())
    assert ev.topic == "flight-watcher.misc"


# --- webhook (SPEC §4.1) ---


@pytest.fixture
async def client(tmp_path):
    from core.state import State
    from ingest.http import create_app
    from tests.helpers import make_brain

    async with State.open(tmp_path / "s.db") as state:
        brain = make_brain(state, tmp_path)
        app = create_app(brain, token="sekrit")
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


async def test_webhook_round_trip_returns_decision(client):
    resp = await client.post(
        "/v1/events", json=PAYLOAD, headers={"Authorization": "Bearer sekrit"}
    )
    assert resp.status_code == 200
    decision = Decision.model_validate(resp.json())
    assert decision.route in ("interrupt", "digest", "dispatch", "curate", "drop")
    assert decision.reason


async def test_webhook_rejects_bad_token(client):
    resp = await client.post(
        "/v1/events", json=PAYLOAD, headers={"Authorization": "Bearer wrong"}
    )
    assert resp.status_code == 401


async def test_webhook_dedups_second_delivery(client):
    h = {"Authorization": "Bearer sekrit"}
    first = await client.post("/v1/events", json=PAYLOAD, headers=h)
    second = await client.post("/v1/events", json=PAYLOAD, headers=h)
    assert first.json()["route"] != "drop"
    assert second.json()["route"] == "drop"
    assert "dedup" in second.json()["matched_rules"]


# --- MCP server (SPEC §4.1) ---


async def test_mcp_tools(tmp_path):
    from fastmcp import Client

    from core.state import State
    from ingest.mcp_server import create_mcp
    from tests.helpers import make_brain

    async with State.open(tmp_path / "s.db") as state:
        brain = make_brain(state, tmp_path)
        mcp = create_mcp(brain)
        async with Client(mcp) as client:
            tools = {t.name for t in await client.list_tools()}
            assert {"propose", "feedback", "digest", "policy", "stats"} <= tools

            result = await client.call_tool("propose", {"event": PAYLOAD})
            assert result.data["route"] in ("interrupt", "digest", "dispatch", "curate", "drop")

            event_id = result.data["event_id"]
            await client.call_tool("feedback", {"event_id": event_id, "signal": "acted"})
            assert (await state.feedback_rows())[0]["signal"] == "acted"

            stats = await client.call_tool("stats", {"days": 7})
            assert stats.data["events_in"] >= 1

            policy_text = await client.call_tool("policy", {"action": "show"})
            assert isinstance(policy_text.data, str)
