"""Step 33 acceptance (SPEC v3.2): local web console.

- every /api route tested incl. 401 without token;
- POLICY.md edits from the UI take effect on the next decision;
- approve/reject transitions a pending task;
- the console page ships in the wheel and serves as HTML.
"""

import httpx
import pytest

from core.learner import Learner
from core.schema import Task
from core.state import State
from tests.helpers import StaticJudge, make_brain

AUTH = {"Authorization": "Bearer sekrit"}


class OkExecutor:
    name = "noop"

    async def run(self, task):
        return "done: " + task.goal


@pytest.fixture
async def console(tmp_path):
    from ingest.http import create_app

    async with State.open(tmp_path / "s.db") as state:
        brain = make_brain(state, tmp_path, judge=StaticJudge())
        app = create_app(brain, token="sekrit", learner=Learner(state),
                         executor=OkExecutor())
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            yield c, brain, state, tmp_path


async def test_ui_page_serves_html_without_token(console):
    c, *_ = console
    resp = await c.get("/ui")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Chief" in resp.text  # the page shell; data calls carry the token


async def test_api_routes_reject_missing_token(console):
    c, *_ = console
    for route in ("/api/overview", "/api/decisions", "/api/digest",
                  "/api/policy", "/api/tasks", "/api/sources"):
        resp = await c.get(route)
        assert resp.status_code == 401, route


async def test_overview_reports_counts_and_health(console):
    c, brain, *_ = console
    await brain.process({"source": "ci", "topic": "dev.ci", "summary": "CI failed on main"})
    resp = await c.get("/api/overview", headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert body["counts"] and body["degraded"] is None
    assert "llm_share" in body["stats"]


async def test_decisions_history_with_search(console):
    c, brain, *_ = console
    await brain.process({"source": "ci", "topic": "dev.ci", "summary": "CI failed on main"})
    await brain.process({"source": "rss", "topic": "news.ai", "summary": "New model released",
                         "dedup_key": "k2"})
    resp = await c.get("/api/decisions", headers=AUTH)
    assert len(resp.json()) == 2
    resp = await c.get("/api/decisions?q=model", headers=AUTH)
    rows = resp.json()
    assert len(rows) == 1 and rows[0]["event"]["topic"] == "news.ai"
    assert rows[0]["decision"]["reason"]  # explainable everywhere


async def test_policy_roundtrip_takes_effect_next_decision(console):
    c, brain, *_ = console
    resp = await c.put("/api/policy", headers=AUTH,
                       json={"text": "## Muted topics\n- spam.deals\n"})
    assert resp.status_code == 200
    assert "spam.deals" in (await c.get("/api/policy", headers=AUTH)).json()["text"]
    decision = await brain.process(
        {"source": "shop", "topic": "spam.deals", "summary": "Huge discount now"})
    assert decision.route == "drop"  # the edit is live immediately


async def test_task_approve_and_reject(console):
    c, _, state, _ = console
    for tid in ("task_a", "task_b"):
        # acceptance_cmd keeps "done is a claim, not a proof" in force even
        # for human-approved runs
        await state.save_task(Task(id=tid, origin_event_id="evt", goal="fix it",
                                   executor="noop", acceptance="fixed",
                                   acceptance_cmd="true"))
    resp = await c.post("/api/tasks/task_a", headers=AUTH, json={"action": "reject"})
    assert resp.status_code == 200
    assert (await state.load_task("task_a")).status == "rejected"

    resp = await c.post("/api/tasks/task_b", headers=AUTH, json={"action": "approve"})
    assert resp.status_code == 200
    assert (await state.load_task("task_b")).status in ("running", "done", "failed")


async def test_sources_view_lists_connector_slots(console):
    c, *_ = console
    body = (await c.get("/api/sources", headers=AUTH)).json()
    names = [s["name"] for s in body]
    assert "webhook" in names and "mcp" in names


def test_console_html_ships_in_the_package():
    from ui import CONSOLE_HTML_PATH

    text = CONSOLE_HTML_PATH.read_text(encoding="utf-8")
    assert text.lstrip().lower().startswith("<!doctype html")
    for needle in ("Today", "History", "Rules", "Tasks", "Sources",
                   "should_interrupt", "should_not_interrupt"):
        assert needle in text
