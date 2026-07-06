"""Implements SPEC §4.5/§4.6: digest building (Connections section, shadow-mode
annotations) and the 03:00 nightly distillation into POLICY.md."""

import re
from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from core.schema import Decision, Event
from core.state import State
from judge.prompts import distill_prompt
from memory.associate import Connection, batch_associate
from memory.store import MemoryStore

SHADOW_MARK = "⚡ would have:"
POLICY_LINE_RE = re.compile(r"^- .+ \(learned \d{4}-\d{2}-\d{2}, source: .+\)$")


@dataclass
class DigestItem:
    event: Event
    decision: Decision

    @property
    def shadow_annotation(self) -> str | None:
        if SHADOW_MARK in self.decision.reason:
            return SHADOW_MARK + self.decision.reason.split(SHADOW_MARK, 1)[1]
        return None


@dataclass
class Digest:
    at: datetime
    items: list[DigestItem] = field(default_factory=list)
    connections: list[Connection] = field(default_factory=list)


async def build_digest(
    state: State, memory: MemoryStore, *, since: datetime, now: datetime
) -> Digest:
    pool = await state.digest_pool(since)
    items = [DigestItem(event=e, decision=d) for e, d in pool]
    connections = await batch_associate(
        memory, [(e.id, e.summary) for e, _ in pool], now=now
    )
    return Digest(at=now, items=items, connections=connections)


def render_digest(digest: Digest) -> str:
    lines = [f"📰 chief digest — {digest.at:%Y-%m-%d %H:%M}", ""]
    if not digest.items:
        lines.append("(nothing worth batching — a quiet stretch)")
    for item in digest.items:
        lines.append(f"• {item.event.summary}")
        if item.shadow_annotation:
            lines.append(f"  {item.shadow_annotation}  [✓ good call / ✗ should have pinged]")
    if digest.connections:
        lines += ["", "Connections"]
        for conn in digest.connections:
            lines.append(f'  ↳ {conn.event_summary} — remembered: "{conn.memory_text}"')
    return "\n".join(lines) + "\n"


async def distill(
    state: State,
    policy_path: str | Path,
    *,
    now: datetime,
    ask: Callable[[str], Awaitable[str]] | None = None,
) -> str | None:
    """Nightly job: translate the day's feedback into ONE human-readable POLICY
    line, format `- {rule} (learned {date}, source: {stats})` (SPEC §4.6)."""
    since = now - timedelta(hours=24)
    rows = [r for r in await state.feedback_rows() if r["at"] >= since.isoformat()]
    per_topic: Counter[tuple[str, str]] = Counter()
    for row in rows:
        event = await state.load_event(row["event_id"])
        if event:
            per_topic[(event.topic, row["signal"])] += 1
    if not per_topic:
        return None

    (topic, signal), count = per_topic.most_common(1)[0]
    date = f"{now:%Y-%m-%d}"
    stats = f"{signal}×{count}"

    line: str | None = None
    if ask:
        changes = "; ".join(f"{t}: {s}×{n}" for (t, s), n in per_topic.most_common())
        raw = (await ask(distill_prompt(date=date, changes=changes))).strip()
        if POLICY_LINE_RE.match(raw):
            line = raw
    if line is None:
        positive = signal in ("acted", "read", "promote", "task_ok")
        verb = "more" if positive else "less"
        line = f"- Deliver {topic} {verb} eagerly (learned {date}, source: {stats})"

    path = Path(policy_path).expanduser()
    text = path.read_text(encoding="utf-8") if path.exists() else "# POLICY\n"
    if "## Learned" not in text:
        text = text.rstrip() + "\n\n## Learned\n"
    text = text.rstrip() + f"\n{line}\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return line
