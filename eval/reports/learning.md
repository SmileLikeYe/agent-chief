# Preference-learning eval — reward loop

_2026-07-06 14:16 UTC · 12 rounds · 7 topics/round_

**Routing agreement: 0% → 100% (+100%)** · converged in 2 round(s)

Reward = user's should/shouldn't-interrupt signal · policy = per-topic weighted routing · training = EMA. No labels, no gradient.

## Learning curve (agreement per round)

```
r 0 |                    | 0%
r 1 |█████████████████   | 86%
r 2 |████████████████████| 100%
r 3 |████████████████████| 100%
r 4 |████████████████████| 100%
r 5 |████████████████████| 100%
r 6 |████████████████████| 100%
r 7 |████████████████████| 100%
r 8 |████████████████████| 100%
r 9 |████████████████████| 100%
r10 |████████████████████| 100%
r11 |████████████████████| 100%
```

## Final learned weights (urgency dim, default 0.20)

- `prod.incident` → 0.28  (want interrupt)
- `oncall.page` → 0.27  (want interrupt)
- `family.urgent` → 0.28  (want interrupt)
- `news.newsletter` → 0.08  (want silence)
- `social.likes` → 0.13  (want silence)
- `ci.flaky` → 0.13  (want silence)
- `marketing.blast` → 0.13  (want silence)
