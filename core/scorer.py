"""Implements SPEC §4.4: the three-stage worthiness engine.

Step 3 ships stage 1 (hard rules, µs). Stages 2-3 arrive in later steps.
"""

import re
from dataclasses import dataclass
from datetime import datetime, time

from core.embedding import DEFAULT_EMBEDDER, Embedder, cosine
from core.policy import Policy

# SPEC §4.4: zero-information template regex
_ZERO_INFO_RE = re.compile(
    r"all (good|clear|normal)|nothing (new|to report)|check(ed)? complete", re.IGNORECASE
)

# Canned "empty report" set for the embedding half of the zero-information test.
_EMPTY_REPORTS = [
    "All clear, nothing to report.",
    "Everything is all normal.",
    "Heartbeat: everything all normal.",
    "Heartbeat check complete, all good.",
    "Nothing new to report, all systems normal.",
    "Nightly check complete, everything all good.",
]
_ZERO_INFO_SIM_THRESHOLD = 0.85


@dataclass
class RuleHit:
    """A stage-1 verdict: forced route + which rule fired + why."""

    route: str
    rule: str
    reason: str


def _parse_quiet_hours(spec: str) -> tuple[time, time]:
    start_s, end_s = spec.split("-")
    parse = lambda s: time(*(int(p) for p in s.strip().split(":")))  # noqa: E731
    return parse(start_s), parse(end_s)


def in_quiet_hours(now: datetime, spec: str) -> bool:
    start, end = _parse_quiet_hours(spec)
    t = now.time()
    if start <= end:
        return start <= t < end
    return t >= start or t < end  # spans midnight


def _topic_in_whitelist(topic: str, whitelist: list[str]) -> bool:
    return any(topic == w or topic.startswith(w + ".") for w in whitelist)


def is_zero_information(summary: str, embedder: Embedder = DEFAULT_EMBEDDER) -> bool:
    """SPEC §4.4: regex AND canned-set embedding similarity > 0.85, both required."""
    if not _ZERO_INFO_RE.search(summary):
        return False
    vec = embedder.embed(summary)
    return any(
        cosine(vec, embedder.embed(canned)) > _ZERO_INFO_SIM_THRESHOLD
        for canned in _EMPTY_REPORTS
    )


def stage1(
    event,
    *,
    now: datetime,
    policy: Policy,
    quiet_hours: str = "23:00-08:00",
    night_whitelist: list[str] | None = None,
    recent_dedup_keys: frozenset[str] | set[str] = frozenset(),
    embedder: Embedder = DEFAULT_EMBEDDER,
) -> RuleHit | None:
    """Stage-1 hard rules (SPEC §4.4). Returns a forced route, or None to continue."""
    night_whitelist = night_whitelist or []

    if in_quiet_hours(now, quiet_hours) and not _topic_in_whitelist(
        event.topic, night_whitelist
    ):
        return RuleHit("digest", "quiet_hours", f"quiet hours {quiet_hours}, topic not whitelisted")

    if policy.is_muted(event.topic):
        return RuleHit("drop", "muted_topic", f"topic {event.topic} muted in POLICY.md")

    if event.dedup_key and event.dedup_key in recent_dedup_keys:
        return RuleHit("drop", "dedup", "duplicate of an event seen in the last 24h")

    if is_zero_information(event.summary, embedder):
        return RuleHit("drop", "zero_information", "zero-information template (empty report)")

    rule = policy.route_for(event.topic)
    if rule:
        return RuleHit(
            rule.route, f"policy:{rule.pattern}", f"POLICY.md rule {rule.pattern} -> {rule.route}"
        )

    return None
