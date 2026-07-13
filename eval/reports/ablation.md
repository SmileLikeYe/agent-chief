# Ablation eval — does each funnel stage earn its keep?

_2026-07-13 09:41 UTC · golden 200 · backend `fixtures` (offline, deterministic)_

**Every stage pays for itself.** Removing stage-1 costs 59 extra judge calls (+42%) **and** drops agreement +20.0%. Removing the judge drops agreement -38.5% to the rules-only floor.

## Cold-path configurations

| configuration | routing agreement | judge calls | rel. LLM cost | illustrative USD |
|---|---|---|---|---|
| full funnel (stage-1 + judge) | 100.0% (200/200) | 141 | 1.00× | $0.0379 |
| −stage-1 (judge-only) | 80.0% (160/200) | 200 | 1.42× | $0.0538 |
| −judge (rules-only / degraded) | 61.5% (123/200) | 0 | 0.00× | $0.0000 |

- **stage-1 (µs hard rules)** resolves 59 of 200 events — +20.0% agreement and a third fewer paid judge calls, from state (mute list, dedup history, wall clock) no per-event LLM call can see.
- **stage-3 (LLM judge)** lifts agreement +38.5% over the rules-only degraded floor — the funnel is not just rules with a language model bolted on; the judge does the discretionary routing.

## Stage-2 (ms similarity cache) — cost on repeat traffic

Stage-2 is a warm cache: on a never-before-seen event it can only *pass* to the judge, so it adds nothing to cold accuracy **by design**. Its job is to make traffic it has seen before nearly free. Against the no-cache baseline, filling the cache as it goes and then replaying identical traffic:

| pass | judge calls | stage-2 short-circuits | agreement |
|---|---|---|---|
| baseline (stage-2 off) | 141 | 0 | 200/200 |
| pass 1 (cache fills as it runs) | 89 | 52 | 199/200 |
| pass 2 (fully warm) | 0 | 141 | 199/200 |

Even a single pass saves 52 of 141 judge calls (37%) on intra-day near-duplicates; on identical repeat traffic the cache erases all 141 (199/200 agreement — the cache is faithful, not free of trade-offs).

## Method & honesty

- Deterministic and offline: the `fixtures` judge replays recorded component scores, so re-running yields identical numbers (pinned in `tests/test_ablation.py`).
- Illustrative USD prices each judge call at nominal DeepSeek tokens (in 1400, cached 1150, out 110) = $0.00027/call. The *ratio* between configs is exact — only the absolute scale depends on this assumption.
- The `−stage-1` config gives events that stage-1 would resolve a neutral verdict (every dimension 0.5), modelling a judge that lacks the mute/dedup/clock context. It is not claimed the judge is weak — it is that those decisions require state a stateless judge call does not have.
