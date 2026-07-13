# Calibration eval — is the routing score trustworthy?

_2026-07-13 09:49 UTC · 7200 held-out interrupt predictions pooled across the 100-user cohort · 45% wanted_

**The score ranks wanted above unwanted with AUC 0.918** after learning (up from 0.368 on uniform weights). Empirical P(wanted) is monotone in the score; a monotone recalibration cuts ECE 0.263 → 0.011.

## Reliability — P(wanted) by score bin

Score mapped to [0,1] by its structural max (5·0.5 = 2.5). A well-ordered decision variable climbs monotonically here.

```
  score bin      P(wanted)              n
  0.1–0.2   |██                  |  10%  (3018)
  0.2–0.3   |██████████          |  51%  (2555)
  0.3–0.4   |████████████████████| 100%  (1477)
  0.4–0.5   |████████████████████| 100%  (106)
  0.5–0.6   |████████████████████| 100%  (44)
```

- **AUC after learning: 0.918** (before: 0.368) — assumption-free ranking quality; learning turns the score into a strong interrupt discriminator.
- **ECE raw: 0.263 → isotonic: 0.011** — the raw score is well-ordered but not natively a probability; a parameter-free monotone map (fit on half, scored on the held-out half) makes it calibrated.

## Per-scene operating points

Each scene's interrupt threshold is a deliberate point on the same score axis — quieter scenes sit lower (more recall), demanding scenes sit higher (more precision):

| scene | threshold | precision | recall | n |
|---|---|---|---|---|
| idle | 0.45 | 94% | 83% | 1728 |
| commuting | 0.60 | 100% | 80% | 1296 |
| social | 0.70 | 98% | 79% | 1080 |
| deep_work | 0.85 | 100% | 58% | 2304 |
| meeting | 0.90 | 100% | 51% | 792 |

## Method & honesty

- A view over `run_cohort()`: same seeded, offline held-out stream, so these numbers are byte-stable and pinned in `tests/test_calibration.py`.
- **AUC needs no probability assumption** — it is pure rank order, the cleanest claim here. The reliability/ECE numbers depend on the disclosed score→[0,1] map (÷2.5); the isotonic step removes that dependence by *learning* the map and is scored on held-out data so it can't memorize.
- Isotonic PAV is a parameter-free monotone fit used only to measure calibratability — it is not added to the routing path (SPEC §13: no heavy ML; the shipped router stays score-vs-threshold).
