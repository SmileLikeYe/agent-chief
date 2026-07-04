"""Implements SPEC §4.1: entry normalization — generate id, fill dedup_key,
infer missing topic via a cheap (cached) LLM call with a heuristic fallback."""

import hashlib
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from core.schema import Event, new_event_id
from judge.prompts import TOPIC_INFER_PROMPT


class TopicInferrer:
    """Cheap LLM topic inference, cached by summary; degrades to `{source}.misc`."""

    def __init__(self, ask: Callable[[str], Awaitable[str]] | None = None):
        self.ask = ask
        self._cache: dict[str, str] = {}

    async def infer(self, summary: str, source: str) -> str:
        if summary in self._cache:
            return self._cache[summary]
        if self.ask is None:
            topic = f"{source}.misc"
        else:
            raw = await self.ask(TOPIC_INFER_PROMPT.format(summary=summary))
            topic = raw.strip().strip('"').strip() or f"{source}.misc"
        self._cache[summary] = topic
        return topic


async def normalize(
    payload: dict,
    *,
    inferrer: TopicInferrer | None = None,
    now: datetime | None = None,
) -> Event:
    """Event without id/received_at → full Event (SPEC §4.1)."""
    now = now or datetime.now(UTC)
    data = dict(payload)
    data.setdefault("id", new_event_id(now))
    data.setdefault("received_at", now)
    if not data.get("dedup_key"):
        data["dedup_key"] = hashlib.sha1(data.get("summary", "").encode()).hexdigest()[:16]
    if not data.get("topic"):
        inferrer = inferrer or TopicInferrer()
        data["topic"] = await inferrer.infer(data.get("summary", ""), data.get("source", "unknown"))
    return Event.model_validate(data)
