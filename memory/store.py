"""Implements SPEC §4.5: memory curation — store, associate (at-ingest lookup),
TTL/archive. No real-time association in v1 (SPEC §13)."""

import secrets
from datetime import datetime, timedelta

from core.embedding import DEFAULT_EMBEDDER, Embedder, cosine
from core.schema import MemoryItem
from core.state import State

ASSOCIATION_THRESHOLD = 0.78  # SPEC §4.2
TOP_K = 3


class MemoryStore:
    def __init__(self, state: State, embedder: Embedder = DEFAULT_EMBEDDER):
        self.state = state
        self.embedder = embedder

    async def curate(
        self, text: str, *, topic: str, origin_event_id: str | None, now: datetime
    ) -> MemoryItem:
        item = MemoryItem(
            id=f"mem_{now:%Y%m%d}_{secrets.token_hex(3)}",
            origin_event_id=origin_event_id,
            text=text,
            topic=topic,
            embedding=self.embedder.embed(text),
            created_at=now,
        )
        await self.state.save_memory(item)
        return item

    async def associate(self, text: str, *, now: datetime) -> list[MemoryItem]:
        """Top-3 active memories with cosine > 0.78; updates hit stats (SPEC §4.2)."""
        query = self.embedder.embed(text)
        scored = [
            (cosine(query, item.embedding), item)
            for item in await self.state.list_memory()
        ]
        hits = sorted(
            (pair for pair in scored if pair[0] > ASSOCIATION_THRESHOLD),
            key=lambda pair: pair[0],
            reverse=True,
        )[:TOP_K]
        results = []
        for _sim, item in hits:
            item.hit_count += 1
            item.last_hit_at = now
            await self.state.save_memory(item)
            results.append(item)
        return results

    async def expire(self, *, now: datetime) -> int:
        """Move items past their ttl_days into the archive table (SPEC §3)."""
        moved = 0
        for item in await self.state.list_memory():
            if now - item.created_at > timedelta(days=item.ttl_days):
                await self.state.save_memory(item, archive=True)
                await self.state.delete_memory(item.id)
                moved += 1
        return moved
