"""Preference-drift benchmark (SPEC v3.2 Step 43 — pin lifecycle).

The cohort benchmark proves Chief learns a *fixed* preference. Real preferences
move: a topic you cared about last quarter stops mattering; a new project starts
demanding your attention. This eval flips each persona's preferences mid-stream
and asks the harder question — **does Chief track a moving target, and does it let
go of what it over-learned?**

Design, per persona (deterministic, offline — same primitives as `eval/cohort.py`):

  phase A   train `ROUNDS_A` rounds against the *original* wants. Some quiet,
            wanted topics get escalated to a hard **pin** (the cohort-v2 ceiling
            break). Snapshot held-out F1 vs the original wants.
  drift     flip the preference: drop one wanted topic (preferring one that got
            pinned, so a pin must now be *un*-learned) and add one previously
            unwanted topic.
  phase B   train `ROUNDS_B` more rounds against the *new* wants. Measure held-out
            F1 vs the new wants both immediately after the flip (un-adapted) and at
            the end (re-adapted), and check the obsolete pin was removed.

The headline is the recovery curve — F1 against the *current* truth: high before
drift, it collapses the instant preferences flip, then climbs back as ±1 feedback
re-teaches the policy. The subplot is un-pinning: a pin the user contradicts with
`should_not_interrupt` is dropped, so an over-learned interrupt doesn't outlive the
preference that created it.
"""

import random
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from statistics import mean

from core.learner import Learner
from core.schema import Decision, Event, SceneState
from core.scorer import DEFAULT_WEIGHTS, score_and_route
from core.state import State
from eval.cohort import (
    BASE,
    EVAL_EVENTS_PER_TOPIC,
    PERSONAS_PATH,
    _f1,
    _result,
    load_cohort,
    reachable,
)

ROUNDS_A = 10  # enough for the cohort to converge + escalate pins
ROUNDS_B = 10  # enough to re-learn the flipped preference


@dataclass
class DriftResult:
    id: str
    scene: str
    noise_tier: str
    dropped: str | None
    added: str | None
    f1_before_drift: float  # vs original wants, end of phase A
    f1_at_drift: float  # vs new wants, immediately after flip (un-adapted)
    f1_after_drift: float  # vs new wants, end of phase B (re-adapted)
    had_pin_on_dropped: bool  # a pin existed on the now-unwanted topic
    pin_removed: bool  # …and phase B tore it down


@dataclass
class DriftReport:
    results: list[DriftResult]
    topics: list[str]
    rounds_a: int = ROUNDS_A
    rounds_b: int = ROUNDS_B
    pinned: list = field(default_factory=list)

    @property
    def n(self) -> int:
        return len(self.results)

    @property
    def f1_before_drift(self) -> float:
        return mean(r.f1_before_drift for r in self.results) if self.results else 0.0

    @property
    def f1_at_drift(self) -> float:
        return mean(r.f1_at_drift for r in self.results) if self.results else 0.0

    @property
    def f1_after_drift(self) -> float:
        return mean(r.f1_after_drift for r in self.results) if self.results else 0.0

    @property
    def recovered_frac(self) -> float:
        """Personas whose post-drift F1 climbs back to within 0.05 of pre-drift."""
        if not self.results:
            return 0.0
        ok = sum(1 for r in self.results if r.f1_after_drift >= r.f1_before_drift - 0.05)
        return ok / self.n

    @property
    def pinned_on_dropped(self) -> list[DriftResult]:
        return [r for r in self.results if r.had_pin_on_dropped]

    @property
    def unpin_frac(self) -> float:
        """Of the personas that had a pin on the now-unwanted topic, how many
        tore it down. This is the un-pinning claim, measured."""
        grp = self.pinned_on_dropped
        if not grp:
            return 0.0
        return sum(1 for r in grp if r.pin_removed) / len(grp)


def _flip(wants: set[str], topics: list[str], strength: dict, thr: float, idx: int):
    """Deterministically pick (drop, add): drop a wanted topic — preferring one a
    pin would guard (unreachable by weights) so the flip exercises un-pinning — and
    add a previously unwanted topic, preferring a reachable one so plain EMA can
    satisfy it. Returns (dropped, added, new_wants)."""
    unwanted = [t for t in topics if t not in wants]
    unreachable_wanted = sorted(t for t in wants if not reachable(strength[t], thr))
    drop_pool = unreachable_wanted or sorted(wants, key=lambda t: (strength[t], t))
    reachable_unwanted = sorted(t for t in unwanted if reachable(strength[t], thr))
    add_pool = reachable_unwanted or sorted(unwanted)
    dropped = drop_pool[idx % len(drop_pool)] if drop_pool else None
    added = add_pool[idx % len(add_pool)] if add_pool else None
    new_wants = set(wants)
    if dropped:
        new_wants.discard(dropped)
    if added:
        new_wants.add(added)
    return dropped, added, new_wants


async def _train(st, learner, prefix, topics, strength, scene, scene_name,
                 wants, noise, rng, rounds, round_offset):
    """Run the ±1 correction loop for `rounds` rounds against `wants`. Identical
    mechanics to the cohort trainer — a pin, once present, forces interrupt."""
    for r in range(rounds):
        gr = round_offset + r
        for i, topic in enumerate(topics):
            w = await st.get_topic_weights(f"{prefix}::{topic}") or dict(DEFAULT_WEIGHTS)
            route, score, comps, _ = score_and_route(
                _result(strength[topic]), scene, topic_weights=w)
            interrupted = route == "interrupt" or await st.is_pinned(f"{prefix}::{topic}")
            wanted = topic in wants
            signal = None
            if interrupted and not wanted:
                signal = "should_not_interrupt"
            elif (not interrupted) and wanted:
                signal = "should_interrupt"
            if signal and rng.random() >= noise:
                at = BASE + timedelta(minutes=gr * 100 + i)
                event = Event(id=f"{prefix}_{gr}_{i}", source="drift",
                              topic=f"{prefix}::{topic}", summary=topic, received_at=at)
                decision = Decision(event_id=event.id, route=route, score=score,
                                    components=comps, scene=scene_name,
                                    scene_confidence=scene.confidence, cost=0.0,
                                    reason="drift", stage=3)
                await st.save_event(event)
                await st.save_decision(decision)
                await learner.record(event, decision, signal, at=at)


async def _heldout_f1(st, prefix, topics, stream, wants, scene) -> tuple[float, set]:
    learned = {t: await st.get_topic_weights(f"{prefix}::{t}") or dict(DEFAULT_WEIGHTS)
               for t in topics}
    pinned = {t for t in topics if await st.is_pinned(f"{prefix}::{t}")}
    _, _, f1, _ = _f1(stream, wants, scene, lambda t: learned[t], pinned=pinned)
    return f1, pinned


async def _run_persona(st, persona, topics, strength, thr_for) -> DriftResult:
    wants_before = set(persona["wants_interrupt"])
    scene_name = persona["scene"]
    scene = SceneState(scene=scene_name, confidence=0.8, signals={}, at=BASE)
    thr = thr_for(scene_name)
    noise = persona["feedback_noise"]
    idx = int(persona["id"].rsplit("_", 1)[-1])
    rng = random.Random(2000 + idx)
    prefix = persona["id"]
    learner = Learner(st)

    eval_rng = random.Random(50000 + idx)
    stream: list[tuple[str, float]] = []
    for topic in topics:
        for _ in range(EVAL_EVENTS_PER_TOPIC):
            stream.append((topic, strength[topic] + eval_rng.uniform(-0.05, 0.05)))

    # phase A — original preferences
    await _train(st, learner, prefix, topics, strength, scene, scene_name,
                 wants_before, noise, rng, ROUNDS_A, 0)
    f1_before, pins_a = await _heldout_f1(st, prefix, topics, stream, wants_before, scene)

    # drift
    dropped, added, wants_after = _flip(wants_before, topics, strength, thr, idx)
    had_pin_on_dropped = dropped in pins_a
    f1_at_drift, _ = await _heldout_f1(st, prefix, topics, stream, wants_after, scene)

    # phase B — new preferences
    await _train(st, learner, prefix, topics, strength, scene, scene_name,
                 wants_after, noise, rng, ROUNDS_A, ROUNDS_A)
    f1_after, pins_b = await _heldout_f1(st, prefix, topics, stream, wants_after, scene)

    return DriftResult(
        id=persona["id"], scene=scene_name, noise_tier=persona["noise_tier"],
        dropped=dropped, added=added,
        f1_before_drift=f1_before, f1_at_drift=f1_at_drift, f1_after_drift=f1_after,
        had_pin_on_dropped=had_pin_on_dropped,
        pin_removed=had_pin_on_dropped and dropped not in pins_b)


async def run_drift(path: str | Path = PERSONAS_PATH) -> DriftReport:
    import tempfile

    from context.infer import interrupt_threshold

    meta, personas = load_cohort(path)
    topics = [t["topic"] for t in meta["topics"]]
    strength = {t["topic"]: t["strength"] for t in meta["topics"]}

    results: list[DriftResult] = []
    with tempfile.TemporaryDirectory() as d:
        async with State.open(Path(d) / "drift.db") as st:
            for persona in personas:
                results.append(
                    await _run_persona(st, persona, topics, strength, interrupt_threshold))
    return DriftReport(results=results, topics=topics)


def render_markdown(report: DriftReport, now=None) -> str:
    from datetime import UTC, datetime
    now = now or datetime.now(UTC)
    bar = lambda v: "█" * round(v * 20)  # noqa: E731
    grp = report.pinned_on_dropped
    lines = [
        "# Preference-drift benchmark",
        "",
        f"_{now:%Y-%m-%d %H:%M} UTC · {report.n} users · {report.rounds_a} rounds "
        f"before drift · {report.rounds_b} after · preferences flip mid-stream_",
        "",
        "**Chief tracks a moving target.** Each user's preferences are flipped after "
        "training (one wanted topic dropped, one unwanted added). Held-out interrupt "
        "F1, scored against the *current* truth at each checkpoint:",
        "",
        "```",
        f"before drift (vs old wants)  {report.f1_before_drift:.2f} "
        f"|{bar(report.f1_before_drift):<20}|  learned",
        f"at drift     (vs new wants)  {report.f1_at_drift:.2f} "
        f"|{bar(report.f1_at_drift):<20}|  ← preferences just flipped",
        f"after drift  (vs new wants)  {report.f1_after_drift:.2f} "
        f"|{bar(report.f1_after_drift):<20}|  re-learned",
        "```",
        "",
        f"F1 collapses the instant preferences flip (**{report.f1_before_drift:.2f} → "
        f"{report.f1_at_drift:.2f}** — Chief is still serving the old preference), then "
        f"±1 feedback climbs it back to **{report.f1_after_drift:.2f}**. "
        f"**{report.recovered_frac:.0%}** of users recover to within 0.05 of their "
        "pre-drift quality.",
        "",
        "## Un-pinning: an over-learned interrupt doesn't outlive its preference",
        "",
        f"Of the **{len(grp)}** users whose dropped topic had been escalated to a hard "
        f"**pin** during phase A, **{report.unpin_frac:.0%}** had that pin **removed** "
        "by phase B — the `should_not_interrupt` corrections the pin provoked tore it "
        "down (`core.learner` → `State.remove_pin`). Without un-pinning, every one of "
        "these would interrupt forever on a topic the user no longer wants.",
        "",
        "## By feedback-noise tier",
        "",
        "| tier | users | F1 before | F1 at drift | F1 after | recovered |",
        "|---|---|---|---|---|---|",
    ]
    for tier in ["clean", "light", "noisy", "erratic"]:
        g = [r for r in report.results if r.noise_tier == tier]
        if not g:
            continue
        rec = sum(1 for r in g if r.f1_after_drift >= r.f1_before_drift - 0.05) / len(g)
        lines.append(
            f"| {tier} | {len(g)} | {mean(r.f1_before_drift for r in g):.2f} | "
            f"{mean(r.f1_at_drift for r in g):.2f} | "
            f"{mean(r.f1_after_drift for r in g):.2f} | {rec:.0%} |")
    lines += [
        "",
        "Noise costs re-learning latency, not the ability to re-learn — the same "
        "shape the fixed-preference cohort shows. Preferences that move are tracked; "
        "pins that go stale are let go.",
        "",
    ]
    return "\n".join(lines)


def write_report(report: DriftReport, path: str | Path | None = None) -> Path:
    path = Path(path) if path else Path(__file__).parent / "reports" / "drift.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_markdown(report), encoding="utf-8")
    return path
