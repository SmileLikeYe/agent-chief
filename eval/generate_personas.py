"""Deterministic generator for eval/personas.jsonl — a 100-user cohort for the
preference-learning benchmark (SPEC v3.2 Step 38).

Why a cohort at all: the single-user reward-loop eval (`eval/learning.py`) proves
the loop *closes* — one simulated user, 0%→100% in two rounds. That is an
anecdote. A product claim ("Chief learns your preferences") is a claim about a
*population*: how fast do people converge on average, how many never do, does
feedback noise break it? This file is the population — 100 users with hidden,
idiosyncratic per-topic interrupt preferences, spread across scenes (thresholds)
and feedback-noise tiers — so `eval/cohort.py` can report a distribution instead
of a single number.

Generation is seeded (`random.Random`) and therefore reproducible: the committed
`personas.jsonl` is exactly what this script emits, and a test pins that.

Run: `uv run python -m eval.generate_personas` (rewrites eval/personas.jsonl).
"""

import json
import random
from pathlib import Path

PERSONAS_PATH = Path(__file__).parent / "personas.jsonl"

N_PERSONAS = 100
SEED = 20260708

# The shared event vocabulary. `strength` is how interrupt-looking a topic is at
# face value (the mean of its five judged components). At uniform weights the
# score equals the strength, so topics with strength ≥ an idle threshold (0.45)
# would interrupt *everyone* by default — which is exactly the noise a real inbox
# has. Learning's job is to override that default per person. `base_want` is how
# commonly people actually want an interrupt for the topic; individual personas
# deviate from it, which is what makes the cohort a spread and not a monolith.
#   topic                strength  base_want
TOPICS = [
    ("prod.incident",       0.44,   0.92),  # urgent + widely wanted, but under-scored
    ("oncall.page",         0.40,   0.88),  # wanted, scored well below the bar
    ("sec.breach",          0.46,   0.90),  # wanted, just at the idle bar
    ("deploy.failed",       0.43,   0.78),  # usually wanted
    ("family.urgent",       0.45,   0.85),  # wanted, personal
    ("review.requested",    0.48,   0.45),  # genuinely split — half want it
    ("ci.flaky",            0.52,   0.25),  # loud but usually unwanted
    ("build.slow",          0.38,   0.20),  # quiet and usually unwanted
    ("finance.digest",      0.38,   0.15),  # rarely an interrupt
    ("social.likes",        0.55,   0.08),  # loud but almost nobody wants it
    ("marketing.blast",     0.66,   0.04),  # loudest, wanted by ~no one
    ("news.newsletter",     0.70,   0.06),  # loudest, wanted by ~no one
]

# chronotype → the scene the person is usually in when events land, which sets
# the interrupt threshold they must clear (context/infer.SCENE_POLICY).
#   name          scene         weight (how common in the cohort)
CHRONOTYPES = [
    ("focused",   "deep_work",  0.30),  # high bar 0.85 — hard to earn an interrupt
    ("relaxed",   "idle",       0.28),  # low bar 0.45
    ("social",    "social",     0.16),  # 0.70
    ("commuter",  "commuting",  0.14),  # 0.60
    ("in_meeting", "meeting",   0.12),  # 0.90 — hardest
]

# feedback-noise tiers: fraction of the time the user fails to give the
# correcting signal (distracted, inconsistent). Higher noise → slower, sometimes
# incomplete convergence. This is the knob that turns a step into a distribution.
NOISE_TIERS = [
    ("clean",  0.00, 0.30),
    ("light",  0.10, 0.34),
    ("noisy",  0.25, 0.24),
    ("erratic", 0.40, 0.12),
]


def _weighted_choice(rng: random.Random, table):
    """table: list of (value, ..., weight) with weight last. Returns the row."""
    total = sum(row[-1] for row in table)
    x = rng.random() * total
    acc = 0.0
    for row in table:
        acc += row[-1]
        if x <= acc:
            return row
    return table[-1]


def _make_persona(i: int) -> dict:
    rng = random.Random(SEED + i * 7919)  # distinct, deterministic per persona
    chrono, scene, _ = _weighted_choice(rng, CHRONOTYPES)
    noise_tier, noise, _ = _weighted_choice(rng, NOISE_TIERS)

    wants = []
    for topic, _strength, base_want in TOPICS:
        # personal deviation from the population base rate, clamped to [0, 1]
        p = min(1.0, max(0.0, base_want + rng.uniform(-0.18, 0.18)))
        if rng.random() < p:
            wants.append(topic)
    # guarantee at least one wanted and one unwanted topic so precision/recall
    # and the agreement curve are both well-defined for every persona
    if not wants:
        wants = [TOPICS[0][0]]
    if len(wants) == len(TOPICS):
        wants = wants[:-1]

    return {
        "type": "persona",
        "id": f"user_{i:03d}",
        "chronotype": chrono,
        "scene": scene,
        "noise_tier": noise_tier,
        "feedback_noise": noise,
        "wants_interrupt": wants,
    }


def build() -> tuple[dict, list[dict]]:
    meta = {
        "type": "meta",
        "n": N_PERSONAS,
        "seed": SEED,
        "topics": [
            {"topic": t, "strength": s, "base_want": b} for t, s, b in TOPICS
        ],
        "chronotypes": [{"name": n, "scene": sc} for n, sc, _ in CHRONOTYPES],
        "noise_tiers": [{"name": n, "noise": nz} for n, nz, _ in NOISE_TIERS],
        "note": "hidden per-topic interrupt preferences for the cohort learning benchmark",
    }
    personas = [_make_persona(i) for i in range(1, N_PERSONAS + 1)]
    return meta, personas


def main() -> None:
    meta, personas = build()
    lines = [json.dumps(meta, ensure_ascii=False)]
    lines += [json.dumps(p, ensure_ascii=False) for p in personas]
    PERSONAS_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    wanted = sum(len(p["wants_interrupt"]) for p in personas)
    print(f"wrote {len(personas)} personas to {PERSONAS_PATH} "
          f"({wanted / len(personas):.1f} wanted topics/user avg)")


if __name__ == "__main__":
    main()
