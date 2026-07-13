# Cohort preference-learning benchmark

_2026-07-13 10:16 UTC · 100 simulated users · 12 train rounds · 12 topics · 6 held-out events/topic_

**95% of users converge** to ≥95% routing agreement (median 5 rounds, p90 8).

**Held-out interrupt F1: 0.10 → 0.87** (mean across 100 users), taught only by ±1 feedback — no labels, no gradient.

Reward = should/shouldn't-interrupt · policy = per-topic weighted routing · training = EMA (`core.learner`). Train and eval streams are disjoint.

## Rounds to converge (≥95% agreement)

```
  round  1 |███                           | 2
  round  2 |██████████████████████████████| 22
  round  3 |████████████████              | 12
  round  4 |███████████████               | 11
  round  5 |███████                       | 5
  round  6 |█████████████████████████     | 18
  round  7 |███████████████               | 11
  round  8 |████████                      | 6
  round  9 |██████████                    | 7
  round 10 |                              | 0
  round 11 |█                             | 1
```

## Mean learning curve (cohort agreement per round)

```
r 0 |██████████          | 48%
r 1 |██████████████      | 69%
r 2 |████████████████    | 78%
r 3 |█████████████████   | 84%
r 4 |██████████████████  | 89%
r 5 |██████████████████  | 92%
r 6 |███████████████████ | 96%
r 7 |███████████████████ | 97%
r 8 |████████████████████| 98%
r 9 |████████████████████| 99%
r10 |████████████████████| 99%
r11 |████████████████████| 100%
```

## By feedback-noise tier

| tier | users | converged | F1 before | F1 after |
|---|---|---|---|---|
| clean | 21 | 100% | 0.10 | 0.87 |
| light | 38 | 100% | 0.09 | 0.86 |
| noisy | 29 | 100% | 0.12 | 0.88 |
| erratic | 12 | 58% | 0.14 | 0.84 |

## The ceiling — and breaking it with pins

36/100 users have at least one wanted topic that EMA weights **cannot** lift over their scene's interrupt bar: weights cap at 0.5, so a topic of face-value strength `s` peaks at score `5s²` and clears threshold `T` only when `s ≥ √(T/5)`. A quiet topic in a deep-work or meeting scene stays below it no matter how many times the user asks — so nudging weights forever is the wrong move.

When a `should_interrupt` correction arrives but the weights have stopped moving, the learner escalates to a **hard per-topic pin** (`core.learner`, SPEC §4.6). That rescues **31 of 36** structurally-capped users — cohort convergence rises from the EMA-only **64%** to **95%**, held-out F1 to **0.87**.

The **5** who still don't converge are erratic users: with the noisiest feedback they never send a pin enough consistent corrections to trigger it inside the training window. The residual ceiling is now **noise-limited, not arithmetic** — the exact, honest shape you'd want.
