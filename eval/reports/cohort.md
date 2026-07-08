# Cohort preference-learning benchmark

_2026-07-08 03:16 UTC · 100 simulated users · 12 train rounds · 12 topics · 6 held-out events/topic_

**64% of users converge** to ≥95% routing agreement (median 3 rounds, p90 7).

**Held-out interrupt F1: 0.10 → 0.81** (mean across 100 users), taught only by ±1 feedback — no labels, no gradient.

Reward = should/shouldn't-interrupt · policy = per-topic weighted routing · training = EMA (`core.learner`). Train and eval streams are disjoint.

## Rounds to converge (≥95% agreement)

```
  round  1 |███                           | 2
  round  2 |██████████████████████████████| 22
  round  3 |████████████████              | 12
  round  4 |███████████████               | 11
  round  5 |███████                       | 5
  round  6 |████                          | 3
  round  7 |████                          | 3
  round  8 |████                          | 3
  round  9 |█                             | 1
  round 10 |███                           | 2
```

## Mean learning curve (cohort agreement per round)

```
r 0 |██████████          | 48%
r 1 |██████████████      | 69%
r 2 |████████████████    | 78%
r 3 |█████████████████   | 84%
r 4 |██████████████████  | 89%
r 5 |██████████████████  | 92%
r 6 |███████████████████ | 94%
r 7 |███████████████████ | 94%
r 8 |███████████████████ | 95%
r 9 |███████████████████ | 95%
r10 |███████████████████ | 96%
r11 |███████████████████ | 96%
```

## By feedback-noise tier

| tier | users | converged | F1 before | F1 after |
|---|---|---|---|---|
| clean | 21 | 71% | 0.10 | 0.82 |
| light | 38 | 61% | 0.09 | 0.80 |
| noisy | 29 | 69% | 0.12 | 0.82 |
| erratic | 12 | 50% | 0.14 | 0.79 |

## The ceiling, stated

36/100 users have at least one wanted topic that preference **cannot** lift over their scene's interrupt bar: EMA weights cap at 0.5, so a topic of face-value strength `s` peaks at score `5s²` and clears threshold `T` only when `s ≥ √(T/5)`. A quiet topic in a deep-work or meeting scene stays below it no matter how many times the user asks. That is why not every user reaches 100% — and it is correct: feedback moves *borderline* decisions; stage-1 rules and clear high/low scores already handle the obvious.
