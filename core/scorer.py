"""Implements SPEC §4.4: the three-stage worthiness engine.

Step 3 ships stage 1 (hard rules, µs). Stages 2-3 arrive in later steps.
"""

import re
from dataclasses import dataclass
from datetime import datetime, time

from core.embedding import DEFAULT_EMBEDDER, Embedder, cosine
from core.policy import Policy
from core.schema import SceneState

# SPEC §4.4: zero-information template regex
_ZERO_INFO_RE = re.compile(
    r"all (good|clear|normal)|nothing (new|to report)|check(ed)? complete", re.IGNORECASE
)

# Canned "empty report" set for the embedding half of the zero-information test.
_EMPTY_REPORTS = [
    "All clear, nothing to report.",
    "Everything is all normal.",
    "Heartbeat: everything all normal.",
    "Heartbeat: all clear, nothing to report.",
    "Heartbeat check complete, all good.",
    "Nothing new to report, all systems normal.",
    "Nightly check complete, everything all good.",
    "Evening check: all good, nothing new.",
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

    # Drop rules run before the quiet-hours digest rule: noise must die even at
    # night, or it would resurface in the morning digest (see §4.7 events 1/24).
    if policy.is_muted(event.topic):
        return RuleHit("drop", "muted_topic", f"topic {event.topic} muted in POLICY.md")

    if event.dedup_key and event.dedup_key in recent_dedup_keys:
        return RuleHit("drop", "dedup", "duplicate of an event seen in the last 24h")

    if is_zero_information(event.summary, embedder):
        return RuleHit("drop", "zero_information", "zero-information template (empty report)")

    if in_quiet_hours(now, quiet_hours) and not _topic_in_whitelist(
        event.topic, night_whitelist
    ):
        return RuleHit("digest", "quiet_hours", f"quiet hours {quiet_hours}, topic not whitelisted")

    rule = policy.route_for(event.topic)
    if rule:
        return RuleHit(
            rule.route, f"policy:{rule.pattern}", f"POLICY.md rule {rule.pattern} -> {rule.route}"
        )

    return None


# --- stage-3 composition & routing (SPEC §4.4) ---

DIMS = ("urgency", "relevance", "actionability", "novelty", "confidence")
DEFAULT_WEIGHTS = {dim: 0.2 for dim in DIMS}
DIGEST_FLOOR = 0.40


def score_and_route(
    result,
    scene: SceneState,
    *,
    topic_weights: dict[str, float] | None = None,
    scene_cost: float = 0.0,
    threshold_overrides: dict[str, float] | None = None,
    memory_hit: bool = False,
) -> tuple[str, float, dict[str, float], str]:
    """Compose `score = Σ(w_topic[dim]·comp[dim]) − scene_cost` and route.

    Returns (route, score, components-after-boost, reason).
    """
    from context.infer import downgrade_low_confidence, interrupt_threshold

    weights = {**DEFAULT_WEIGHTS, **(topic_weights or {})}
    comps = {dim: getattr(result, dim) for dim in DIMS}
    if memory_hit:
        comps["relevance"] = min(1.0, comps["relevance"] * 1.2)

    score = sum(weights[dim] * comps[dim] for dim in DIMS) - scene_cost
    threshold = interrupt_threshold(scene.scene, threshold_overrides)

    if score >= threshold:
        route = "interrupt"
        reason = f"score {score:.2f} ≥ {scene.scene} threshold {threshold:.2f}"
    elif score >= DIGEST_FLOOR:
        route = "digest"
        reason = f"score {score:.2f} below {scene.scene} threshold {threshold:.2f}"
    elif result.memorize:
        route = "curate"
        reason = f"score {score:.2f} low but worth remembering"
    else:
        route = "drop"
        reason = f"score {score:.2f} with no lasting value"

    route = downgrade_low_confidence(route, scene)
    if route == "digest" and score >= threshold:
        reason += f"; downgraded (scene confidence {scene.confidence:.2f} < 0.6)"

    # SPEC §4.4: dispatchable prep work runs first, then delivery ("arrive with a plan")
    if result.dispatchable and route in ("interrupt", "digest"):
        route = "dispatch"
        reason += "; dispatchable prep work available"

    return route, score, comps, reason
