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
    # natural feedback (SPEC v3.2 Step 32): the user said it outright, so it
    # outweighs every inferred signal
    "should_interrupt": (0.35, +1),
    "should_not_interrupt": (0.35, -1),
}

# every signal any surface may submit (HTTP/MCP/Telegram/UI validate against this)
KNOWN_SIGNALS = frozenset(SIGNAL_EFFECTS) | {
    "promote", "muted", "task_ok", "task_fail", "shadow_good", "shadow_bad",
}


async def apply_feedback(state, event_id: str, signal: str, at, classifier=None) -> bool:
    """One entry point behind every surface (HTTP/MCP/Telegram/UI): validate the
    signal, then learn from it when the event+decision are still on hand,
    otherwise just record the row. Returns True iff weights were updated."""
    if signal not in KNOWN_SIGNALS:
        raise ValueError(f"unknown feedback signal: {signal!r}")
    event = await state.load_event(event_id)
    decision = await state.load_decision(event_id)
    if event and decision:
        await Learner(state, classifier=classifier).record(event, decision, signal, at=at)
        return True
    await state.save_feedback(event_id, signal, at)
    return False

WEIGHT_MIN, WEIGHT_MAX = 0.02, 0.5
THRESHOLD_MIN, THRESHOLD_MAX = 0.35, 0.95
PROPENSITY_ALPHA = 0.2
# The ceiling escalation (SPEC §4.6): EMA weights only pull toward the event's
# components, so a wanted-but-quiet topic converges below its scene's interrupt
# bar and stays there. When a `should_interrupt` correction arrives but the
# weight update has all but stopped moving, EMA has demonstrably run out of room
# — escalate to a hard per-topic pin instead of nudging forever.
PIN_CONVERGENCE_EPS = 0.01
# A pin is a hard, content-blind override that fires on *every* event of its
# topic, so an explicit `should_not_interrupt` on a pinned topic is a direct
# contradiction of the pin's whole reason to exist — remove it at once (unlike
# creation, which must overcome EMA inertia, removal of an explicit pin on an
# explicit counter-signal is safe). And a pin no event has re-fired in this many
# days has outlived its usefulness → the nightly job prunes it.
PIN_STALE_DAYS = 30


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

    async def rebuild_classifier(self) -> None:
        """Reseed the stage-2 engaged/dismissed sets from persisted feedback
        history (join to events for the summary text). Called at startup."""
        if not self.classifier:
            return
        for row in await self.state.feedback_rows():
            event = await self.state.load_event(row["event_id"])
            if not event:
                continue
            if row["signal"] in ("acted", "read", "promote"):
                decision = await self.state.load_decision(event.id)
                self.classifier.add_engaged(
                    event.summary, decision.route if decision else "digest"
                )
            elif row["signal"] == "dismissed_fast":
                self.classifier.add_dismissed(event.summary)

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
            moved = 0.0
            for dim in DIMS:
                target = comps.get(dim, 0.0) if direction > 0 else 0.0
                w = (1 - alpha) * weights[dim] + alpha * target
                w = min(WEIGHT_MAX, max(WEIGHT_MIN, w))
                moved = max(moved, abs(w - weights[dim]))
                weights[dim] = w
            await self.state.set_topic_weights(event.topic, weights)
            # ceiling escalation: still being told to interrupt, but the weights
            # have stopped moving → a nudge can't help; pin the topic outright.
            if (
                signal == "should_interrupt"
                and moved < PIN_CONVERGENCE_EPS
                and not await self.state.is_pinned(event.topic)
            ):
                await self.state.add_pin(event.topic, at)
            # de-escalation: the user is explicitly telling a pinned topic to stop
            # interrupting — honour it immediately ("stop flagging this"). The pin
            # forced the interrupt they just rejected, so one counter-signal is
            # enough; the decayed weights below keep it from re-pinning by accident.
            elif signal == "should_not_interrupt":
                await self.state.remove_pin(event.topic)

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


THRESHOLD_KEY = "__threshold_adjust__"


async def load_threshold_adjust(state: State) -> float:
    stored = await state.get_topic_weights(THRESHOLD_KEY)
    return stored.get("adjust", 0.0) if stored else 0.0


async def daily_threshold_tuning(state: State, *, now: datetime) -> float:
    """SPEC §4.6: 7-day interrupt dismissed_fast ratio >40% → +0.02/day,
    <15% → −0.01/day. Persists and returns the new global adjustment."""
    since = now - timedelta(days=7)
    interrupts = (await state.route_counts(since=since)).get("interrupt", 0)
    dismissed = await state.count_feedback(signal="dismissed_fast", since=since)
    adjust = await load_threshold_adjust(state)
    if interrupts > 0:
        adjust = tune_adjust(adjust, dismissed / interrupts)
        await state.set_topic_weights(THRESHOLD_KEY, {"adjust": adjust})
    return adjust


async def prune_stale_pins(state: State, *, now: datetime) -> list[str]:
    """Nightly: drop learned pins no event has re-fired in PIN_STALE_DAYS, so the
    pin set stays a live reflection of what the user still wants flagged."""
    return await state.prune_stale_pins(now=now, max_idle_days=PIN_STALE_DAYS)


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
    # cost dimension (SPEC v3.1 Step 26)
    llm_share: float = 0.0  # fraction of events that reached the LLM judge
    cache_hit_rate: float = 0.0  # cached input tokens / all input tokens
    judgment_cost: float = 0.0  # total USD spent on judgments


async def build_tact_report(state: State, *, days: int, now: datetime) -> TactReport:
    since = now - timedelta(days=days)
    counts = await state.route_counts(since=since)
    good = await state.count_feedback(signal="shadow_good", since=since)
    bad = await state.count_feedback(signal="shadow_bad", since=since)
    stats = await state.decision_stats(since=since)
    return TactReport(
        days=days,
        events_in=sum(counts.values()),
        blocked=counts.get("drop", 0),
        batched=counts.get("digest", 0),
        handled=counts.get("dispatch", 0),
        interrupted=counts.get("interrupt", 0),
        graded=good + bad,
        accuracy=(good, good + bad),
        llm_share=stats["judged"] / stats["total"] if stats["total"] else 0.0,
        cache_hit_rate=(
            stats["cached_tokens"] / stats["tokens_in"] if stats["tokens_in"] else 0.0
        ),
        judgment_cost=stats["usd_cost"],
    )
