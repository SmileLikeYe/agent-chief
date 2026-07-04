"""Step 17 acceptance: #5→#19 chain — curate, then hit, then Connections entry;
TTL expiry excludes archived items from association."""

from datetime import UTC, datetime, timedelta

from core.state import State
from memory.associate import batch_associate
from memory.store import MemoryStore

T0 = datetime(2026, 7, 6, 9, 30, tzinfo=UTC)

# the demo #5 → #19 texts (SPEC §4.7 anchor chain)
MEMORIZE = "watch for XX SDK 2.0 release announcement"
EVENT_19 = "RSS: XX SDK 2.0 release announcement"


async def test_curate_then_hit_chain(tmp_path):
    async with State.open(tmp_path / "s.db") as state:
        store = MemoryStore(state)
        item = await store.curate(MEMORIZE, topic="dev.sdk_release",
                                  origin_event_id="evt_demo_05", now=T0)
        assert item.embedding

        hits = await store.associate(EVENT_19, now=T0 + timedelta(hours=7))
        assert [h.text for h in hits] == [MEMORIZE]

        # hit stats updated (SPEC §4.2 step 2)
        stored = await state.load_memory(item.id)
        assert stored.hit_count == 1 and stored.last_hit_at is not None


async def test_unrelated_event_no_hit(tmp_path):
    async with State.open(tmp_path / "s.db") as state:
        store = MemoryStore(state)
        await store.curate(MEMORIZE, topic="dev.sdk_release", origin_event_id="e", now=T0)
        assert await store.associate("Marketing webinar about cloud spend", now=T0) == []


async def test_top3_cap(tmp_path):
    async with State.open(tmp_path / "s.db") as state:
        store = MemoryStore(state)
        for i in range(5):
            await store.curate(f"watch for XX SDK 2.0 release announcement variant {i}",
                               topic="dev.sdk_release", origin_event_id=f"e{i}", now=T0)
        hits = await store.associate(EVENT_19, now=T0)
        assert len(hits) <= 3


async def test_ttl_expiry_archives_and_excludes(tmp_path):
    async with State.open(tmp_path / "s.db") as state:
        store = MemoryStore(state)
        old = await store.curate(MEMORIZE, topic="dev.sdk_release",
                                 origin_event_id="e", now=T0 - timedelta(days=100))
        fresh = await store.curate("keep an eye on Postgres 18 GA date",
                                   topic="db.postgres", origin_event_id="e2", now=T0)
        moved = await store.expire(now=T0)
        assert moved == 1

        # archived → no longer associable
        assert await store.associate(EVENT_19, now=T0) == []
        # still recallable from the archive table, gone from active
        assert await state.load_memory(old.id) is None
        assert await state.load_memory(fresh.id) is not None


async def test_digest_batch_association_builds_connections(tmp_path):
    async with State.open(tmp_path / "s.db") as state:
        store = MemoryStore(state)
        await store.curate(MEMORIZE, topic="dev.sdk_release", origin_event_id="evt_demo_05",
                           now=T0)
        pool = [
            ("evt_demo_19", EVENT_19),
            ("evt_demo_08", "JavaScript Weekly #712: new bundler benchmarks"),
        ]
        connections = await batch_associate(store, pool, now=T0 + timedelta(hours=9))
        assert len(connections) == 1
        conn = connections[0]
        assert conn.event_id == "evt_demo_19"
        assert conn.memory_text == MEMORIZE
