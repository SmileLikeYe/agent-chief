"""Step 8 acceptance: demo-script routing agreement ≥ 20/24 against recorded
HTTP cassettes; malformed-JSON retry; config-driven backend selection."""

import json

import httpx
import pytest

from demo.runner import load_fixture, replay
from judge.anthropic import AnthropicJudge
from judge.base import JudgeContext, JudgeError
from judge.deepseek import DeepSeekJudge
from judge.factory import make_judge
from judge.fixtures import FixtureJudge
from judge.ollama import OllamaJudge
from judge.openai import OpenAIJudge
from judge.prompts import SYSTEM_PROMPT, context_block, user_block

GOOD_JSON = json.dumps(
    {
        "urgency": 0.9,
        "relevance": 0.8,
        "actionability": 0.7,
        "novelty": 0.6,
        "confidence": 0.9,
        "dispatchable": False,
        "dispatch_goal": None,
        "memorize": None,
        "reason": "cassette",
    }
)


def make_event():
    from datetime import UTC, datetime

    from core.schema import Event

    return Event(
        id="evt_x",
        source="t",
        topic="dev.ci",
        summary="CI failed",
        received_at=datetime(2026, 7, 6, tzinfo=UTC),
    )


def openai_style_response(content: str) -> dict:
    return {"choices": [{"message": {"content": content}}]}


def transport_returning(bodies: list[dict], calls: list) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=bodies[min(len(calls) - 1, len(bodies) - 1)])

    return httpx.MockTransport(handler)


# --- malformed JSON retry ---


async def test_malformed_json_retries_then_succeeds():
    calls: list = []
    transport = transport_returning(
        [openai_style_response("I think it's urgent!"), openai_style_response(GOOD_JSON)], calls
    )
    judge = DeepSeekJudge(model="deepseek-chat", api_key="k", transport=transport)
    result = await judge.judge(make_event(), JudgeContext())
    assert result.urgency == 0.9
    assert len(calls) == 2


async def test_malformed_json_exhausts_retries():
    calls: list = []
    transport = transport_returning([openai_style_response("nope")], calls)
    judge = DeepSeekJudge(model="deepseek-chat", api_key="k", transport=transport)
    with pytest.raises(JudgeError):
        await judge.judge(make_event(), JudgeContext())
    assert len(calls) == 2  # one retry


async def test_json_in_code_fence_is_accepted():
    transport = transport_returning(
        [openai_style_response(f"```json\n{GOOD_JSON}\n```")], []
    )
    judge = OpenAIJudge(model="gpt-4o-mini", api_key="k", transport=transport)
    result = await judge.judge(make_event(), JudgeContext())
    assert result.relevance == 0.8


# --- adapter wire formats ---


async def test_ollama_adapter():
    calls: list = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content))
        return httpx.Response(200, json={"message": {"content": GOOD_JSON}})

    judge = OllamaJudge(model="qwen3:4b", transport=httpx.MockTransport(handler))
    result = await judge.judge(make_event(), JudgeContext())
    assert result.urgency == 0.9
    assert calls[0]["model"] == "qwen3:4b"
    assert calls[0]["format"] == "json"
    assert calls[0]["messages"][0]["content"] == SYSTEM_PROMPT


async def test_anthropic_adapter():
    calls: list = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((dict(request.headers), json.loads(request.content)))
        return httpx.Response(200, json={"content": [{"type": "text", "text": GOOD_JSON}]})

    judge = AnthropicJudge(
        model="claude-haiku-4-5", api_key="k", transport=httpx.MockTransport(handler)
    )
    result = await judge.judge(make_event(), JudgeContext())
    assert result.confidence == 0.9
    headers, body = calls[0]
    assert headers["x-api-key"] == "k"
    assert body["system"] == SYSTEM_PROMPT
    assert body["temperature"] == 0


# --- prompt structure (SPEC §4.4: stable prefix, cache-friendly) ---


def test_system_prompt_is_the_gatekeeper():
    assert SYSTEM_PROMPT.startswith("You are the gatekeeper of the user's attention.")
    assert "do not disturb" in SYSTEM_PROMPT
    assert "Output JSON only" in SYSTEM_PROMPT


def test_context_and_user_blocks():
    ctx = JudgeContext(
        user_profile="engineer",
        recent_deliveries=["a"],
        associated_memory=["watch sdk"],
        scene="meeting",
        scene_confidence=0.85,
    )
    c = context_block(ctx)
    assert "engineer" in c and "watch sdk" in c
    u = user_block(make_event(), ctx)
    assert "meeting" in u and "CI failed" in u


# --- config-driven selection ---


@pytest.mark.parametrize(
    ("backend", "cls"),
    [
        ("ollama", OllamaJudge),
        ("deepseek", DeepSeekJudge),
        ("anthropic", AnthropicJudge),
        ("openai", OpenAIJudge),
        ("fixtures", FixtureJudge),
    ],
)
def test_factory_selects_backend(backend, cls):
    judge = make_judge({"backend": backend, "model": "m", "api_key": "k"})
    assert isinstance(judge, cls)


def test_factory_rejects_unknown_backend():
    with pytest.raises(ValueError):
        make_judge({"backend": "skynet"})


# --- demo-script routing agreement ≥ 20/24 via recorded cassettes ---


def test_demo_routing_agreement_with_cassette_judge():
    """Recorded per-event responses (cassettes) served over a mock HTTP judge;
    the full demo replay must agree with the expected table on ≥ 20/24 routes."""
    fixture = load_fixture()
    cassettes = {
        e.event["id"]: json.dumps(e.judge) for e in fixture.entries if e.judge
    }

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        prompt = body["messages"][-1]["content"]
        for event_id, recorded in cassettes.items():
            if f'"{event_id}"' in prompt:
                return httpx.Response(200, json=openai_style_response(recorded))
        return httpx.Response(200, json=openai_style_response(GOOD_JSON))

    judge = DeepSeekJudge(
        model="deepseek-chat", api_key="k", transport=httpx.MockTransport(handler)
    )
    results = replay(fixture, judge=judge)
    agreement = sum(1 for r in results if r.decision.route == r.entry.expected_route)
    assert agreement >= 20, f"only {agreement}/24 routes agree"
