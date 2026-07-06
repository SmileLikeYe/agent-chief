"""Preference-learning harness (SPEC v3.2 Step 37): does feedback actually
teach Chief? This closes the reward loop the rest of the system implies —

    reward   = user feedback (should / shouldn't-interrupt, ±1)
    policy   = score_and_route(components, per-topic weights)
    training = EMA weight update in core/learner.py::Learner.record
    eval     = routing agreement vs the user's true preference, over rounds

A simulated user has hidden per-topic preferences. Chief starts blind
(uniform weights) and is corrected only by the ±1 signal — no labels, no
gradient, no heavy ML (SPEC §13). A rising agreement curve is the proof that
the reward signal trains the policy; a flat curve would be a regression.

Deterministic and offline: same seed of events every run.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from core.learner import Learner
from core.schema import Decision, Event, SceneState
from core.scorer import DEFAULT_WEIGHTS, score_and_route
from core.state import State
from judge.base import JudgeResult

BASE = datetime(2026, 7, 6, 9, 0, tzinfo=UTC)

# A synthetic inbox: each topic has a hidden "want interrupt?" truth and a
# component strength (how interrupt-looking it is at face value). At uniform
# weights strong topics interrupt and weak ones don't, regardless of what the
# user actually wants — so wrong topics need 1–3 nudges to cross the threshold.
# The spread of strengths is what makes the learning curve a ramp, not a step.
#   (topic, wants_interrupt, strength)
INBOX = [
    ("prod.incident", True, 0.42),    # wanted but under-scored → train UP
    ("oncall.page", True, 0.40),      # wanted, further under → more nudges
    ("family.urgent", True, 0.44),    # wanted, just under
    ("news.newsletter", False, 0.70), # unwanted but loud → train DOWN hard
    ("social.likes", False, 0.55),    # unwanted, moderately loud
    ("ci.flaky", False, 0.52),        # unwanted, mildly loud
    ("marketing.blast", False, 0.66), # unwanted, loud
]
WANTED = [t for t, want, _ in INBOX if want]
UNWANTED = [t for t, want, _ in INBOX if not want]
STRENGTH = {t: s for t, _, s in INBOX}


@dataclass
class SimUser:
    """Hidden ground truth: which topics deserve an interrupt."""

    wants_interrupt: set[str]

    def desired(self, topic: str) -> str:
        return "interrupt" if topic in self.wants_interrupt else "silent"

    def agrees(self, topic: str, route: str) -> bool:
        return (route == "interrupt") == (topic in self.wants_interrupt)

    def feedback(self, topic: str, route: str) -> str | None:
        """The only supervision Chief gets: a nudge when it guessed wrong."""
        interrupted = route == "interrupt"
        should = topic in self.wants_interrupt
        if interrupted and not should:
            return "should_not_interrupt"
        if not interrupted and should:
            return "should_interrupt"
        return None  # the user is content — no signal, as in real life


@dataclass
class LearningReport:
    rounds: int
    curve: list[float]  # agreement after each round
    final_weights: dict[str, dict]
    events_per_round: int
    baseline: float = field(init=False)
    final: float = field(init=False)

    def __post_init__(self):
        self.baseline = self.curve[0] if self.curve else 0.0
        self.final = self.curve[-1] if self.curve else 0.0

    @property
    def improved(self) -> float:
        return self.final - self.baseline

    @property
    def rounds_to_converge(self) -> int | None:
        """First round at ≥95% agreement (None if never)."""
        for r, v in enumerate(self.curve):
            if v >= 0.95:
                return r
        return None


def _result(strength: float) -> JudgeResult:
    return JudgeResult(reason="sim", urgency=strength, relevance=strength,
                       actionability=strength, novelty=strength, confidence=strength)


async def run_learning(rounds: int = 12, state: State | None = None) -> LearningReport:
    """Run the closed loop for `rounds`; return the agreement curve."""
    topics = [t for t, _, _ in INBOX]
    user = SimUser(wants_interrupt=set(WANTED))

    async def _loop(st: State) -> LearningReport:
        learner = Learner(st)
        scene = SceneState(scene="idle", confidence=0.8, signals={}, at=BASE)
        curve: list[float] = []
        for r in range(rounds):
            agreed = 0
            for i, topic in enumerate(topics):
                weights = await st.get_topic_weights(topic)
                route, score, comps, _ = score_and_route(
                    _result(STRENGTH[topic]), scene, topic_weights=weights)
                agreed += user.agrees(topic, route)
                signal = user.feedback(topic, route)
                if signal:
                    at = BASE + timedelta(minutes=r * 100 + i)
                    event = Event(id=f"evt_{r}_{i}", source="sim", topic=topic,
                                  summary=f"{topic} event", received_at=at)
                    decision = Decision(event_id=event.id, route=route, score=score,
                                        components=comps, scene=scene.scene,
                                        scene_confidence=scene.confidence, cost=0.0,
                                        reason="sim", stage=3)
                    await st.save_event(event)
                    await st.save_decision(decision)
                    await learner.record(event, decision, signal, at=at)
            curve.append(agreed / len(topics))
        final_weights = {
            t: (await st.get_topic_weights(t)) or dict(DEFAULT_WEIGHTS) for t in topics
        }
        return LearningReport(rounds=rounds, curve=curve,
                              final_weights=final_weights, events_per_round=len(topics))

    if state is not None:
        return await _loop(state)
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as d:
        async with State.open(Path(d) / "learn.db") as st:
            return await _loop(st)


def render_markdown(report: LearningReport, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    bar = lambda v: "█" * round(v * 20)  # noqa: E731
    lines = [
        "# Preference-learning eval — reward loop",
        "",
        f"_{now:%Y-%m-%d %H:%M} UTC · {report.rounds} rounds · "
        f"{report.events_per_round} topics/round_",
        "",
        f"**Routing agreement: {report.baseline:.0%} → {report.final:.0%} "
        f"({report.improved:+.0%})** · "
        f"converged in {report.rounds_to_converge} round(s)",
        "",
        "Reward = user's should/shouldn't-interrupt signal · policy = per-topic "
        "weighted routing · training = EMA. No labels, no gradient.",
        "",
        "## Learning curve (agreement per round)",
        "",
        "```",
    ]
    for r, v in enumerate(report.curve):
        lines.append(f"r{r:>2} |{bar(v):<20}| {v:.0%}")
    lines += ["```", "", "## Final learned weights (urgency dim, default 0.20)", ""]
    for topic, w in report.final_weights.items():
        want = "want interrupt" if topic in WANTED else "want silence"
        lines.append(f"- `{topic}` → {w['urgency']:.2f}  ({want})")
    lines.append("")
    return "\n".join(lines)
