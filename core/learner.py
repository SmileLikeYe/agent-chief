"""Implements SPEC §4.6: feedback signals, EMA weight adaptation, threshold
tuning, shadow mode, and the Tact Report.

EMA semantics (ADR): positive signals pull the topic's 5-dim weights toward the
event's component vector; negative signals decay them toward zero. Explainable,
bounded, no heavy ML (SPEC §13).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from core.schema import Decision, Event
from core.scorer import DEFAULT_WEIGHTS, DIMS, SimilarityClassifier
from core.state import State

# signal → (alpha, direction); direction +1 pulls toward components, -1 toward zero
SIGNAL_EFFECTS: dict[str, tuple[float, int]] = {
    "acted": (0.2, +1),
    "read": (0.1, +1),
    "dismissed_fast": (0.2, -1),
    "timeout": (0.05, -1),
}

WEIGHT_MIN, WEIGHT_MAX = 0.02, 0.5
THRESHOLD_MIN, THRESHOLD_MAX = 0.35, 0.95
PROPENSITY_ALPHA = 0.2


def tune_adjust(adjust: float, dismissed_fast_ratio: float) -> float:
    """One day of global-threshold tuning: >40% dismissed → +0.02, <15% → −0.01."""
    if dismissed_fast_ratio > 0.40:
        return adjust + 0.02
    if dismissed_fast_ratio < 0.15:
        return adjust - 0.01
    return adjust


def effective_threshold(
    scene: str, adjust: float, overrides: dict[str, float] | None = None
) -> float:
    """Scene threshold + learned global adjustment, clamped to [0.35, 0.95]."""
    from context.infer import interrupt_threshold

    base = interrupt_threshold(scene, overrides)
    return min(THRESHOLD_MAX, max(THRESHOLD_MIN, base + adjust))


class Learner:
    URGENCY_CAP = 0.5  # promote bumps urgency weight, capped

    def __init__(self, state: State, classifier: SimilarityClassifier | None = None):
        self.state = state
        self.classifier = classifier

    async def topic_weights(self, topic: str) -> dict[str, float]:
        stored = await self.state.get_topic_weights(topic)
        return stored or dict(DEFAULT_WEIGHTS)

    async def dispatch_propensity(self, executor: str, topic: str) -> float:
        stored = await self.state.get_topic_weights(f"dispatch::{executor}::{topic}")
        return stored.get("propensity", 0.5) if stored else 0.5

    async def record(
        self,
        event: Event,
        decision: Decision,
        signal: str,
        *,
        at: datetime,
        executor: str | None = None,
    ) -> None:
        """Apply one SPEC §4.6 signal: feedback row + weight/set/propensity updates."""
        await self.state.save_feedback(event.id, signal, at)

        if signal in SIGNAL_EFFECTS:
            alpha, direction = SIGNAL_EFFECTS[signal]
            comps = decision.components or {}
            weights = await self.topic_weights(event.topic)
            for dim in DIMS:
                target = comps.get(dim, 0.0) if direction > 0 else 0.0
                w = (1 - alpha) * weights[dim] + alpha * target
                weights[dim] = min(WEIGHT_MAX, max(WEIGHT_MIN, w))
            await self.state.set_topic_weights(event.topic, weights)

        if signal == "promote":
            weights = await self.topic_weights(event.topic)
            weights["urgency"] = min(self.URGENCY_CAP, weights["urgency"] + 0.3)
            await self.state.set_topic_weights(event.topic, weights)

        if signal in ("task_ok", "task_fail") and executor:
            key = f"dispatch::{executor}::{event.topic}"
            stored = await self.state.get_topic_weights(key) or {"propensity": 0.5}
            target = 1.0 if signal == "task_ok" else 0.0
            stored["propensity"] = (
                (1 - PROPENSITY_ALPHA) * stored["propensity"] + PROPENSITY_ALPHA * target
            )
            await self.state.set_topic_weights(key, stored)

        if self.classifier:
            if signal in ("acted", "read", "promote"):
                self.classifier.add_engaged(event.summary, decision.route)
            elif signal == "dismissed_fast":
                self.classifier.add_dismissed(event.summary)
        # "muted" is handled at the delivery layer (POLICY.md append, Principle 3).


# --- shadow mode (SPEC §4.6) ---


class ShadowMode:
    """First 7 days (or until 50 feedback samples): every interrupt degrades
    into the digest, annotated with the would-have decision."""

    DAYS = 7
    SAMPLES = 50
    _KEY = "__shadow__"

    def __init__(self, state: State):
        self.state = state

    async def ensure_started(self, now: datetime) -> None:
        if not await self.state.get_topic_weights(self._KEY):
            await self.state.set_topic_weights(self._KEY, {"started_at": now.isoformat()})

    async def active(self, now: datetime) -> bool:
        stored = await self.state.get_topic_weights(self._KEY)
        if not stored:
            return False
        started = datetime.fromisoformat(stored["started_at"])
        if now - started >= timedelta(days=self.DAYS):
            return False
        return await self.state.count_feedback() < self.SAMPLES

    async def apply(self, decision: Decision, *, now: datetime) -> tuple[str, str | None]:
        """Returns (route, digest annotation or None)."""
        if decision.route == "interrupt" and await self.active(now):
            annotation = (
                f"⚡ would have: interrupted you "
                f"(score {decision.score:.2f}, scene {decision.scene})"
            )
            return "digest", annotation
        return decision.route, None


# --- Tact Report (SPEC §4.6/§5) ---


@dataclass
class TactReport:
    days: int
    events_in: int
    blocked: int
    batched: int
    handled: int
    interrupted: int
    graded: int
    accuracy: tuple[int, int]  # (good grades, total grades)


async def build_tact_report(state: State, *, days: int, now: datetime) -> TactReport:
    counts = await state.route_counts()
    since = now - timedelta(days=days)
    good = await state.count_feedback(signal="shadow_good", since=since)
    bad = await state.count_feedback(signal="shadow_bad", since=since)
    return TactReport(
        days=days,
        events_in=sum(counts.values()),
        blocked=counts.get("drop", 0),
        batched=counts.get("digest", 0),
        handled=counts.get("dispatch", 0),
        interrupted=counts.get("interrupt", 0),
        graded=good + bad,
        accuracy=(good, good + bad),
    )
