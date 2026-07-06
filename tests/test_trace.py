"""Step 26 acceptance (SPEC v3.1): decision trace + cost accounting.

- trace renders a complete chain (stages, rules, scores, prompt version, cost);
- unit tests for cost math incl. the DeepSeek cache-hit/miss price gap;
- Tact Report shows % events reaching LLM, cache hit rate, total judgment cost.
"""

import json

import httpx
import pytest
from typer.testing import CliRunner

from core.learner import build_tact_report
from core.state import State
from judge.deepseek import DeepSeekJudge
from judge.pricing import PRICES, usd_cost
from tests.helpers import FIXED_NOW, StaticJudge, make_brain

PAYLOAD = {
    "source": "ci",
    "topic": "dev.ci",
    "summary": "CI failed on main: fixture drift in test_auth_flow",
    "claimed_urgency": "high",
}


# --- cost math ---------------------------------------------------------------


def test_deepseek_cache_hit_is_cheaper_than_miss():
    p = PRICES["deepseek"]
    assert p["input_cache_hit"] < p["input_cache_miss"]  # the gap is the point


def test_usd_cost_math_with_cache_split():
    # 1000 in (600 cached), 200 out on deepseek: exact expected dollars
    p = PRICES["deepseek"]
    expected = (
        400 / 1e6 * p["input_cache_miss"]
        + 600 / 1e6 * p["input_cache_hit"]
        + 200 / 1e6 * p["output"]
    )
    assert usd_cost("deepseek", tokens_in=1000, tokens_out=200, cached=600) == pytest.approx(
        expected
    )
    # all-miss costs strictly more than 60%-cached
    assert usd_cost("deepseek", 1000, 200, 0) > usd_cost("deepseek", 1000, 200, 600)


def test_local_and_fixture_backends_cost_zero():
    assert usd_cost("ollama", 5000, 500, 0) == 0.0
    assert usd_cost("fixtures", 5000, 500, 0) == 0.0


# --- trace recorded on decisions ----------------------------------------------


async def test_stage1_decision_has_trace_without_judge(tmp_path):
    async with State.open(tmp_path / "s.db") as state:
        brain = make_brain(state, tmp_path)
        decision = await brain.process(
            {"source": "hb", "topic": "ops.heartbeat",
             "summary": "Heartbeat: all clear, nothing to report"}
        )
        assert decision.route == "drop"
        t = decision.trace
        assert t is not None
        names = [s.stage for s in t.stages]
        assert "stage1" in names and "judge" not in names
        assert t.usd_cost == 0.0
        assert all(s.ms >= 0 for s in t.stages)


async def test_full_pipeline_trace_has_all_stages_and_version(tmp_path):
    async with State.open(tmp_path / "s.db") as state:
        brain = make_brain(state, tmp_path, judge=StaticJudge())
        decision = await brain.process(dict(PAYLOAD))
        t = decision.trace
        names = [s.stage for s in t.stages]
        for stage in ("stage1", "associate", "judge", "route"):
            assert stage in names, names
        assert t.prompt_version  # stamped on every judged decision
        assert t.backend == "static"


async def test_http_judge_usage_flows_into_trace_cost(tmp_path):
    body = {
        "choices": [{"message": {"content": json.dumps({
            "urgency": 0.8, "relevance": 0.8, "actionability": 0.8,
            "novelty": 0.8, "confidence": 0.8, "dispatchable": False,
            "dispatch_goal": None, "memorize": None, "reason": "ok"})}}],
        "usage": {"prompt_tokens": 1000, "completion_tokens": 100,
                  "prompt_cache_hit_tokens": 600},
    }
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json=body))
    judge = DeepSeekJudge(model="deepseek-chat", api_key="k", transport=transport)
    async with State.open(tmp_path / "s.db") as state:
        brain = make_brain(state, tmp_path, judge=judge)
        decision = await brain.process(dict(PAYLOAD))
        t = decision.trace
        assert (t.tokens_in, t.tokens_out, t.cached_tokens) == (1000, 100, 600)
        assert t.usd_cost == pytest.approx(usd_cost("deepseek", 1000, 100, 600))
        assert decision.cost == pytest.approx(t.usd_cost)


# --- chief trace CLI -----------------------------------------------------------


def test_cli_trace_renders_complete_chain(tmp_path, monkeypatch):
    monkeypatch.setenv("CHIEF_HOME", str(tmp_path))
    import asyncio

    from core.config import db_path

    async def seed():
        async with State.open(db_path()) as state:
            brain = make_brain(state, tmp_path, judge=StaticJudge())
            return await brain.process(dict(PAYLOAD))

    decision = asyncio.run(seed())

    from cli.main import app

    result = CliRunner().invoke(app, ["trace", decision.event_id])
    assert result.exit_code == 0, result.output
    out = result.output
    for needle in ("stage1", "judge", "route", "score", "prompt", "$"):
        assert needle in out, f"missing {needle!r} in trace output"


def test_cli_trace_unknown_event_fails_cleanly(tmp_path, monkeypatch):
    monkeypatch.setenv("CHIEF_HOME", str(tmp_path))
    from cli.main import app

    result = CliRunner().invoke(app, ["trace", "evt_nope"])
    assert result.exit_code == 1


# --- tact report cost dimension -------------------------------------------------


async def test_tact_report_cost_dimension(tmp_path):
    async with State.open(tmp_path / "s.db") as state:
        brain = make_brain(state, tmp_path, judge=StaticJudge())
        # one stage-1 kill (no LLM) + two judged events
        await brain.process({"source": "hb", "topic": "ops.heartbeat",
                             "summary": "Heartbeat: all clear, nothing to report"})
        await brain.process(dict(PAYLOAD))
        await brain.process({**PAYLOAD, "summary": "Deploy pipeline stuck on approval gate",
                             "dedup_key": "other"})
        report = await build_tact_report(state, days=7, now=FIXED_NOW)
        assert 0 < report.llm_share < 1  # 2 of 3 reached the judge
        assert report.cache_hit_rate == 0.0  # StaticJudge reports no usage
        assert report.judgment_cost == 0.0
