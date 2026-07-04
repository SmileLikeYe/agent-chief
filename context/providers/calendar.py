"""Implements SPEC §4.3: calendar provider — current / next-15-min event kind.

Events come from a minimal ICS parser (url or file, optional). No gcal in v1 core;
the provider degrades to empty signals when unconfigured.
"""

import re
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

_EVENT_RE = re.compile(r"BEGIN:VEVENT(.*?)END:VEVENT", re.DOTALL)
_FIELD_RE = re.compile(r"^(DTSTART|DTEND|SUMMARY)[^:]*:(.*)$", re.MULTILINE)

_KIND_KEYWORDS = [
    ("commute", "commute"),
    ("focus", "focus"),
    ("deep work", "focus"),
]


@dataclass
class CalendarEvent:
    start: datetime
    end: datetime
    summary: str

    @property
    def kind(self) -> str:
        low = self.summary.lower()
        for keyword, kind in _KIND_KEYWORDS:
            if keyword in low:
                return kind
        return "meeting"


def _parse_dt(value: str) -> datetime:
    value = value.strip()
    if value.endswith("Z"):
        return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
    return datetime.strptime(value, "%Y%m%dT%H%M%S")


def parse_ics(text: str) -> list[CalendarEvent]:
    """Minimal VEVENT parser: DTSTART / DTEND / SUMMARY only."""
    events = []
    for block in _EVENT_RE.findall(text):
        fields = dict(_FIELD_RE.findall(block))
        if "DTSTART" in fields and "DTEND" in fields:
            events.append(
                CalendarEvent(
                    start=_parse_dt(fields["DTSTART"]),
                    end=_parse_dt(fields["DTEND"]),
                    summary=fields.get("SUMMARY", "").strip(),
                )
            )
    return events


def load_ics(source: str) -> list[CalendarEvent]:
    if source.startswith(("http://", "https://")):
        with urllib.request.urlopen(source, timeout=10) as resp:  # noqa: S310
            return parse_ics(resp.read().decode("utf-8", errors="replace"))
    return parse_ics(Path(source).expanduser().read_text(encoding="utf-8"))


class CalendarProvider:
    name = "calendar"

    def __init__(
        self,
        events: list[CalendarEvent] | None = None,
        source: str | None = None,
        now_fn: Callable[[], datetime] = lambda: datetime.now(UTC),
    ):
        self._events = events
        self.source = source
        self.now_fn = now_fn

    def _load(self) -> list[CalendarEvent]:
        if self._events is not None:
            return self._events
        if self.source:
            return load_ics(self.source)
        return []

    def sample(self) -> dict[str, Any]:
        now = self.now_fn()
        current, upcoming = None, None
        for ev in self._load():
            if ev.start <= now < ev.end:
                current = current or ev
            elif now < ev.start <= now + timedelta(minutes=15):
                upcoming = upcoming or ev
        return {
            "calendar_now": current.kind if current else None,
            "calendar_next_15min": upcoming.kind if upcoming else None,
        }
