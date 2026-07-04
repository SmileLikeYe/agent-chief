"""Implements SPEC §4.2/§4.5: digest-time batch association — cross-event
combinations become the digest's "Connections" section."""

from dataclasses import dataclass
from datetime import datetime

from memory.store import MemoryStore


@dataclass
class Connection:
    event_id: str
    event_summary: str
    memory_text: str
    memory_id: str


async def batch_associate(
    store: MemoryStore, pool: list[tuple[str, str]], *, now: datetime
) -> list[Connection]:
    """One association pass over the day's digest pool [(event_id, summary), ...]."""
    connections = []
    for event_id, summary in pool:
        for item in await store.associate(summary, now=now):
            connections.append(
                Connection(
                    event_id=event_id,
                    event_summary=summary,
                    memory_text=item.text,
                    memory_id=item.id,
                )
            )
    return connections
