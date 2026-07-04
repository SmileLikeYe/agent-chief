"""Step 2 acceptance: model round-trips (create → persist → load → equality),
db file created at configured path, all 8 tables present, audit JSONL writer."""

import json
from datetime import UTC, datetime

from core.schema import Decision, Event, MemoryItem, SceneState, Task, new_event_id
from core.state import TABLES, State

NOW = datetime(2026, 7, 4, 10, 0, tzinfo=UTC)


def make_event(**kw) -> Event:
    defaults = dict(
        id=new_event_id(NOW),
        source="flight-watcher",
        topic="travel.flight_change",
        summary="Flight CA123 delayed 2.5h",
        detail="New departure 18:40",
        suggested_action="Check rebooking options",
        evidence=["https://example.com/status"],
        claimed_urgency="high",
        dedup_key="abc123",
        received_at=NOW,
    )
    defaults.update(kw)
    return Event(**defaults)


async def test_db_file_created_at_configured_path(tmp_path):
    db = tmp_path / "nested" / "state.db"
    async with State.open(db) as state:
        assert db.exists()
        names = await state.table_names()
        assert set(TABLES) <= set(names)
        assert len(TABLES) == 8


async def test_event_round_trip(tmp_path):
    ev = make_event()
    async with State.open(tmp_path / "s.db") as state:
        await state.save_event(ev)
        assert await state.load_event(ev.id) == ev


async def test_decision_round_trip(tmp_path):
    d = Decision(
        event_id="evt_x",
        route="interrupt",
        score=0.91,
        components={"urgency": 0.9, "relevance": 0.8},
        scene="idle",
        scene_confidence=0.4,
        cost=0.45,
        matched_rules=["night_whitelist"],
        reason="high urgency flight change",
        stage=3,
        dispatch_task_id="task_1",
    )
    async with State.open(tmp_path / "s.db") as state:
        await state.save_decision(d)
        assert await state.load_decision(d.event_id) == d


async def test_task_round_trip(tmp_path):
    t = Task(
        id="task_1",
        origin_event_id="evt_x",
        goal="Find rebooking options",
        executor="claude_code",
        acceptance="3 viable alternatives listed",
        acceptance_cmd=None,
        status="pending",
        attempts=0,
    )
    async with State.open(tmp_path / "s.db") as state:
        await state.save_task(t)
        assert await state.load_task(t.id) == t


async def test_memory_item_round_trip(tmp_path):
    m = MemoryItem(
        id="mem_1",
        origin_event_id="evt_x",
        text="user wants to watch XX's next SDK release",
        topic="dev.sdk_release",
        embedding=[0.1, 0.2, 0.3],
        created_at=NOW,
        last_hit_at=None,
        hit_count=0,
        ttl_days=90,
    )
    async with State.open(tmp_path / "s.db") as state:
        await state.save_memory(m)
        assert await state.load_memory(m.id) == m


async def test_scene_state_round_trip(tmp_path):
    s = SceneState(scene="deep_work", confidence=0.75, signals={"foreground": "ide"}, at=NOW)
    async with State.open(tmp_path / "s.db") as state:
        await state.log_scene(s)
        assert (await state.recent_scenes(1))[0] == s


def test_event_id_format():
    eid = new_event_id(NOW)
    assert eid.startswith("evt_20260704_1000_")
    suffix = eid.rsplit("_", 1)[1]
    assert len(suffix) == 4
    int(suffix, 16)  # 4 hex chars


def test_audit_jsonl_writer(tmp_path):
    from core.state import AuditLog

    log = AuditLog(tmp_path / "logs" / "audit.jsonl")
    log.write({"event_id": "evt_x", "route": "drop"})
    log.write({"event_id": "evt_y", "route": "digest"})
    lines = (tmp_path / "logs" / "audit.jsonl").read_text().splitlines()
    assert [json.loads(line)["event_id"] for line in lines] == ["evt_x", "evt_y"]
