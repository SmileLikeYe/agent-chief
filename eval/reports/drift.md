# Preference-drift benchmark

_2026-07-19 12:39 UTC · 100 users · 10 rounds before drift · 10 after · preferences flip mid-stream_

**Chief tracks a moving target.** Each user's preferences are flipped after training (one wanted topic dropped, one unwanted added). Held-out interrupt F1, scored against the *current* truth at each checkpoint:

```
before drift (vs old wants)  0.86 |█████████████████   |  learned
at drift     (vs new wants)  0.69 |██████████████      |  ← preferences just flipped
after drift  (vs new wants)  0.88 |██████████████████  |  re-learned
```

F1 collapses the instant preferences flip (**0.86 → 0.69** — Chief is still serving the old preference), then ±1 feedback climbs it back to **0.88**. **91%** of users recover to within 0.05 of their pre-drift quality.

## Un-pinning: an over-learned interrupt doesn't outlive its preference

Of the **30** users whose dropped topic had been escalated to a hard **pin** during phase A, **100%** had that pin **removed** by phase B — the `should_not_interrupt` corrections the pin provoked tore it down (`core.learner` → `State.remove_pin`). Without un-pinning, every one of these would interrupt forever on a topic the user no longer wants.

## By feedback-noise tier

| tier | users | F1 before | F1 at drift | F1 after | recovered |
|---|---|---|---|---|---|
| clean | 21 | 0.87 | 0.68 | 0.87 | 81% |
| light | 38 | 0.86 | 0.68 | 0.87 | 89% |
| noisy | 29 | 0.87 | 0.69 | 0.89 | 97% |
| erratic | 12 | 0.79 | 0.71 | 0.89 | 100% |

Noise costs re-learning latency, not the ability to re-learn — the same shape the fixed-preference cohort shows. Preferences that move are tracked; pins that go stale are let go.
