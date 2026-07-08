"""Cohort preference-learning benchmark (SPEC v3.2 Step 38).

`eval/learning.py` proves the reward loop closes for *one* user. This runs the
same loop over the 100-user cohort in `personas.jsonl` and reports a
*distribution* — because "Chief learns your preferences" is a claim about a
population, not an anecdote.

Design — a train/eval split, the same shape a real ML benchmark uses:

  train  each persona is corrected only by ±1 feedback (should / shouldn't
         interrupt), with a per-persona noise rate that sometimes withholds the
         signal. We record the agreement curve and the round it converges.
  eval   we then route a *held-out* stream (K jittered events per topic, unseen
         during training) with the learned weights and score interrupt
         precision / recall / F1 — before vs after learning.

Everything reuses production code: `core.learner.Learner.record` for the EMA
update and `core.scorer.score_and_route` for routing. Deterministic and offline
(seeded jitter, fixtures judge) — the numbers in the docs are the numbers you
get.

The ceiling is stated, not hidden: EMA weights are capped at 0.5, so a wanted
topic can only reach score 5·min(0.5,s)·s = 5s². It can clear a scene threshold
T only when s ≥ √(T/5). Wanted-but-quiet topics in demanding scenes are
therefore unreachable by preference alone — feedback moves *borderline*
decisions, which is the whole job.
"""

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import mean

from core.learner import Learner
from core.schema import Decision, Event, SceneState
from core.scorer import DEFAULT_WEIGHTS, score_and_route
from core.state import State
from judge.base import JudgeResult

PERSONAS_PATH = Path(__file__).parent / "personas.jsonl"
BASE = datetime(2026, 7, 8, 9, 0, tzinfo=UTC)

TRAIN_ROUNDS = 12
EVAL_EVENTS_PER_TOPIC = 6  # held-out stream size per topic
WEIGHT_CAP = 0.5  # core.learner.WEIGHT_MAX — the source of the recall ceiling


def load_cohort(path: str | Path = PERSONAS_PATH) -> tuple[dict, list[dict]]:
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    meta = json.loads(lines[0])
    personas = [json.loads(line) for line in lines[1:] if line.strip()]
    return meta, personas


def _result(strength: float) -> JudgeResult:
    s = min(1.0, max(0.0, strength))
    return JudgeResult(reason="cohort", urgency=s, relevance=s,
                       actionability=s, novelty=s, confidence=s)


def reachable(strength: float, threshold: float) -> bool:
    """Can preference alone push this topic over the bar? (5·min(.5,s)·s ≥ T)"""
    return 5 * min(WEIGHT_CAP, strength) * strength >= threshold


@dataclass
class PersonaResult:
    id: str
    scene: str
    noise_tier: str
    noise: float
    curve: list[float]
    converged_round: int | None
    n_wanted: int
    n_unreachable: int  # wanted topics preference can never lift (the ceiling)
    f1_before: float
    f1_after: float
    precision_after: float
    recall_after: float

    @property
    def baseline(self) -> float:
        return self.curve[0] if self.curve else 0.0

    @property
    def final(self) -> float:
        return self.curve[-1] if self.curve else 0.0


@dataclass
class CohortReport:
    results: list[PersonaResult]
    rounds: int
    topics: list[str]
    thresholds: dict[str, float]
    events_per_topic: int = EVAL_EVENTS_PER_TOPIC
    mean_curve: list[float] = field(default_factory=list)

    @property
    def n(self) -> int:
        return len(self.results)

    @property
    def converged(self) -> list[PersonaResult]:
        return [r for r in self.results if r.converged_round is not None]

    @property
    def converged_frac(self) -> float:
        return len(self.converged) / self.n if self.n else 0.0

    @property
    def ceiling_capped(self) -> list[PersonaResult]:
        """Personas that cannot reach 100% because a wanted topic is unreachable."""
        return [r for r in self.results if r.n_unreachable > 0]

    def convergence_pct(self, p: float) -> int | None:
        rounds = sorted(r.converged_round for r in self.converged)
        if not rounds:
            return None
        idx = min(len(rounds) - 1, int(round(p * (len(rounds) - 1))))
        return rounds[idx]

    @property
    def f1_before(self) -> float:
        return mean(r.f1_before for r in self.results) if self.results else 0.0

    @property
    def f1_after(self) -> float:
        return mean(r.f1_after for r in self.results) if self.results else 0.0

    def by_noise(self) -> list[tuple[str, int, float, float, float]]:
        """(tier, n, converged_frac, mean f1_before, mean f1_after), tier order."""
        order = ["clean", "light", "noisy", "erratic"]
        rows = []
        for tier in order:
            grp = [r for r in self.results if r.noise_tier == tier]
            if not grp:
                continue
            cf = sum(1 for r in grp if r.converged_round is not None) / len(grp)
            rows.append((tier, len(grp), cf,
                         mean(r.f1_before for r in grp), mean(r.f1_after for r in grp)))
        return rows


def _f1(events: list[tuple[str, float]], wants: set[str], scene: SceneState,
        weights_by_topic) -> tuple[float, float, float]:
    """Interrupt precision/recall/F1 over a held-out event stream."""
    tp = fp = fn = 0
    for topic, strength in events:
        w = weights_by_topic(topic)
        route, *_ = score_and_route(_result(strength), scene, topic_weights=w)
        predicted = route == "interrupt"
        wanted = topic in wants
        tp += predicted and wanted
        fp += predicted and not wanted
        fn += (not predicted) and wanted
    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return precision, recall, f1


async def _run_persona(st: State, persona: dict, topics, strength, threshold,
                       rounds: int) -> PersonaResult:
    from context.infer import interrupt_threshold

    wants = set(persona["wants_interrupt"])
    scene_name = persona["scene"]
    scene = SceneState(scene=scene_name, confidence=0.8, signals={}, at=BASE)
    thr = interrupt_threshold(scene_name)
    noise = persona["feedback_noise"]
    # deterministic per-persona noise draws — seed from the id's index, NOT
    # hash() (str hashing is salted per-process → would break reproducibility)
    import random
    idx = int(persona["id"].rsplit("_", 1)[-1])
    rng = random.Random(1000 + idx)

    learner = Learner(st)
    prefix = persona["id"]

    async def weights_for(topic):
        return await st.get_topic_weights(f"{prefix}::{topic}") or dict(DEFAULT_WEIGHTS)

    curve: list[float] = []
    for r in range(rounds):
        agreed = 0
        for i, topic in enumerate(topics):
            w = await weights_for(topic)
            route, score, comps, _ = score_and_route(
                _result(strength[topic]), scene, topic_weights=w)
            interrupted = route == "interrupt"
            wanted = topic in wants
            agreed += interrupted == wanted
            # the user only signals when Chief guessed wrong — and even then may
            # stay silent at their personal noise rate
            signal = None
            if interrupted and not wanted:
                signal = "should_not_interrupt"
            elif (not interrupted) and wanted:
                signal = "should_interrupt"
            if signal and rng.random() >= noise:
                at = BASE + timedelta(minutes=r * 100 + i)
                # namespace the topic per persona so 100 users don't share weights
                event = Event(id=f"{prefix}_{r}_{i}", source="cohort",
                              topic=f"{prefix}::{topic}", summary=topic, received_at=at)
                decision = Decision(event_id=event.id, route=route, score=score,
                                    components=comps, scene=scene_name,
                                    scene_confidence=scene.confidence, cost=0.0,
                                    reason="cohort", stage=3)
                await st.save_event(event)
                await st.save_decision(decision)
                await learner.record(event, decision, signal, at=at)
        curve.append(agreed / len(topics))

    # held-out eval: K jittered events per topic, unseen during training
    eval_rng = random.Random(50000 + idx)
    stream: list[tuple[str, float]] = []
    for topic in topics:
        for _ in range(EVAL_EVENTS_PER_TOPIC):
            jitter = eval_rng.uniform(-0.05, 0.05)
            stream.append((topic, strength[topic] + jitter))

    def uniform_w(_topic):
        return dict(DEFAULT_WEIGHTS)

    learned = {t: await weights_for(t) for t in topics}
    _, _, f1_before = _f1(stream, wants, scene, uniform_w)
    p_after, r_after, f1_after = _f1(stream, wants, scene, lambda t: learned[t])

    unreachable = sum(1 for t in wants if not reachable(strength[t], thr))
    converged = next((r for r, v in enumerate(curve) if v >= 0.95), None)
    return PersonaResult(
        id=persona["id"], scene=scene_name, noise_tier=persona["noise_tier"],
        noise=noise, curve=curve, converged_round=converged,
        n_wanted=len(wants), n_unreachable=unreachable,
        f1_before=f1_before, f1_after=f1_after,
        precision_after=p_after, recall_after=r_after)


async def run_cohort(rounds: int = TRAIN_ROUNDS,
                     path: str | Path = PERSONAS_PATH) -> CohortReport:
    from context.infer import interrupt_threshold

    meta, personas = load_cohort(path)
    topics = [t["topic"] for t in meta["topics"]]
    strength = {t["topic"]: t["strength"] for t in meta["topics"]}
    thresholds = {sc: interrupt_threshold(sc)
                  for sc in {p["scene"] for p in personas}}

    import tempfile

    results: list[PersonaResult] = []
    with tempfile.TemporaryDirectory() as d:
        # one DB, weights namespaced per persona — keeps the loop identical to
        # production (real State) without 100 separate files
        async with State.open(Path(d) / "cohort.db") as st:
            for persona in personas:
                results.append(
                    await _run_persona(st, persona, topics, strength, thresholds, rounds))

    max_len = max((len(r.curve) for r in results), default=0)
    mean_curve = [mean(r.curve[i] for r in results) for i in range(max_len)]
    return CohortReport(results=results, rounds=rounds, topics=topics,
                        thresholds=thresholds, mean_curve=mean_curve)


def _hist(values: list[int], width: int = 30) -> list[str]:
    if not values:
        return ["  (none converged)"]
    lo, hi = min(values), max(values)
    buckets: dict[int, int] = {}
    for v in values:
        buckets[v] = buckets.get(v, 0) + 1
    peak = max(buckets.values())
    lines = []
    for r in range(lo, hi + 1):
        c = buckets.get(r, 0)
        bar = "█" * round(c / peak * width) if c else ""
        lines.append(f"  round {r:>2} |{bar:<{width}}| {c}")
    return lines


def render_markdown(report: CohortReport, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    bar = lambda v: "█" * round(v * 20)  # noqa: E731
    p50 = report.convergence_pct(0.50)
    p90 = report.convergence_pct(0.90)
    capped = report.ceiling_capped
    lines = [
        "# Cohort preference-learning benchmark",
        "",
        f"_{now:%Y-%m-%d %H:%M} UTC · {report.n} simulated users · "
        f"{report.rounds} train rounds · {len(report.topics)} topics · "
        f"{report.events_per_topic} held-out events/topic_",
        "",
        f"**{report.converged_frac:.0%} of users converge** to ≥95% routing "
        f"agreement (median {p50} rounds, p90 {p90}).",
        "",
        f"**Held-out interrupt F1: {report.f1_before:.2f} → {report.f1_after:.2f}** "
        f"(mean across {report.n} users), taught only by ±1 feedback — no labels, "
        "no gradient.",
        "",
        "Reward = should/shouldn't-interrupt · policy = per-topic weighted routing "
        "· training = EMA (`core.learner`). Train and eval streams are disjoint.",
        "",
        "## Rounds to converge (≥95% agreement)",
        "",
        "```",
        *_hist([r.converged_round for r in report.converged]),
        "```",
        "",
        "## Mean learning curve (cohort agreement per round)",
        "",
        "```",
    ]
    for r, v in enumerate(report.mean_curve):
        lines.append(f"r{r:>2} |{bar(v):<20}| {v:.0%}")
    lines += [
        "```",
        "",
        "## By feedback-noise tier",
        "",
        "| tier | users | converged | F1 before | F1 after |",
        "|---|---|---|---|---|",
    ]
    for tier, n, cf, f1b, f1a in report.by_noise():
        lines.append(f"| {tier} | {n} | {cf:.0%} | {f1b:.2f} | {f1a:.2f} |")
    lines += [
        "",
        "## The ceiling, stated",
        "",
        f"{len(capped)}/{report.n} users have at least one wanted topic that "
        "preference **cannot** lift over their scene's interrupt bar: EMA weights "
        "cap at 0.5, so a topic of face-value strength `s` peaks at score `5s²` and "
        "clears threshold `T` only when `s ≥ √(T/5)`. A quiet topic in a "
        "deep-work or meeting scene stays below it no matter how many times the "
        "user asks. That is why not every user reaches 100% — and it is correct: "
        "feedback moves *borderline* decisions; stage-1 rules and clear high/low "
        "scores already handle the obvious.",
        "",
    ]
    return "\n".join(lines)
