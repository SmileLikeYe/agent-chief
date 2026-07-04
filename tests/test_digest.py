"""Step 21 acceptance: distillation turns a weight-change log into a well-formed
POLICY line; digest golden-file test (Connections + shadow annotations)."""

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

from core.digest import build_digest, distill, render_digest
from core.policy import parse_policy
from core.schema import Decision, Event
from core.state import State
from memory.store import MemoryStore

NOW = datetime(2026, 7, 6, 18, 30, tzinfo=UTC)
GOLDEN = Path(__file__).parent / "golden" / "digest.txt"

POLICY_LINE_RE = re.compile(r"^- .+ \(learned \d{4}-\d{2}-\d{2}, source: .+\)$")


def ev(id, summary, topic="news.misc", at=NOW - timedelta(hours=2)):
    return Event(id=id, source="t", topic=topic, summary=summary, received_at=at)


def dec(event_id, route="digest", reason="score 0.42", score=0.42):
    return Decision(
        event_id=event_id, route=route, score=score, scene="idle",
        scene_confidence=0.8, cost=0.0, reason=reason, stage=3,
    )


async def seed(state):
    store = MemoryStore(state)
    await store.curate("watch for XX SDK 2.0 release announcement",
                       topic="dev.sdk_release", origin_event_id="evt_0",
                       now=NOW - timedelta(days=1))
    await state.save_event(ev("evt_1", "JavaScript Weekly #712: new bundler benchmarks"))
    await state.save_decision(dec("evt_1"))
    await state.save_event(ev("evt_2", "RSS: XX SDK 2.0 release announcement",
                              topic="dev.sdk_release"))
    await state.save_decision(dec("evt_2"))
    await state.save_event(ev("evt_3", "Competitor Relay ships v3.0"))
    await state.save_decision(
        dec("evt_3", reason="score 0.88; ⚡ would have: interrupted you "
                            "(score 0.88, scene deep_work)", score=0.88)
    )
    return store


async def test_digest_includes_items_connections_and_shadow(tmp_path):
    async with State.open(tmp_path / "s.db") as state:
        store = await seed(state)
        digest = await build_digest(state, store, since=NOW - timedelta(hours=12), now=NOW)
        assert len(digest.items) == 3
        assert len(digest.connections) == 1
        assert digest.connections[0].memory_text == "watch for XX SDK 2.0 release announcement"
        shadow_items = [i for i in digest.items if i.shadow_annotation]
        assert len(shadow_items) == 1
        assert "would have: interrupted you" in shadow_items[0].shadow_annotation


async def test_digest_golden_file(tmp_path):
    async with State.open(tmp_path / "s.db") as state:
        store = await seed(state)
        digest = await build_digest(state, store, since=NOW - timedelta(hours=12), now=NOW)
        rendered = render_digest(digest)
        assert rendered == GOLDEN.read_text(encoding="utf-8")


# --- nightly distillation (SPEC §4.6, 03:00) ---


async def test_distill_llm_path_appends_well_formed_line(tmp_path):
    policy_file = tmp_path / "POLICY.md"
    async with State.open(tmp_path / "s.db") as state:
        for _ in range(4):
            await state.save_feedback("evt_x", "dismissed_fast", NOW)
        await state.save_event(ev("evt_x", "Newsletter blast", topic="news.newsletter"))

        async def ask(prompt):
            assert "news.newsletter" in prompt
            return ("- Deliver news.newsletter less eagerly "
                    "(learned 2026-07-06, source: 4 quick dismissals)")

        line = await distill(state, policy_file, now=NOW, ask=ask)
        assert POLICY_LINE_RE.match(line)
        text = policy_file.read_text()
        assert line in text and "## Learned" in text
        parse_policy(text)  # never crashes on learned prose


async def test_distill_heuristic_path(tmp_path):
    policy_file = tmp_path / "POLICY.md"
    async with State.open(tmp_path / "s.db") as state:
        for _ in range(3):
            await state.save_feedback("evt_y", "acted", NOW)
        await state.save_event(ev("evt_y", "CI failed on main", topic="dev.ci"))
        line = await distill(state, policy_file, now=NOW)
        assert POLICY_LINE_RE.match(line), line
        assert "dev.ci" in line


async def test_distill_no_feedback_appends_nothing(tmp_path):
    policy_file = tmp_path / "POLICY.md"
    async with State.open(tmp_path / "s.db") as state:
        line = await distill(state, policy_file, now=NOW)
        assert line is None
        assert not policy_file.exists()


async def test_scheduler_tick_fires_digest_once(tmp_path, capsys):
    from cli.runtime import tick_jobs
    from delivery.terminal import TerminalChannel

    async with State.open(tmp_path / "s.db") as state:
        store = await seed(state)
        fired: set = set()
        channels = [TerminalChannel()]
        await tick_jobs(state, store, tmp_path / "POLICY.md", channels,
                        ["18:30"], NOW, fired)
        await tick_jobs(state, store, tmp_path / "POLICY.md", channels,
                        ["18:30"], NOW, fired)  # same minute → no double send
        out = capsys.readouterr().out
        assert out.count("chief digest") == 1


async def test_scheduler_tick_runs_distillation_at_3am(tmp_path):
    from cli.runtime import tick_jobs

    async with State.open(tmp_path / "s.db") as state:
        store = MemoryStore(state)
        await state.save_feedback("evt_z", "dismissed_fast", NOW)
        await state.save_event(ev("evt_z", "Newsletter blast", topic="news.newsletter"))
        three_am = NOW.replace(hour=3, minute=0)
        await tick_jobs(state, store, tmp_path / "POLICY.md", [], ["08:00"], three_am, set())
        assert "## Learned" in (tmp_path / "POLICY.md").read_text()
