# Progress

| Step | Title | Status | Commit | Date |
|------|-------|--------|--------|------|
| 1 | Project scaffold | ✅ | 169c5c8 | 2026-07-04 |
| 2 | Core schemas & storage | ✅ | edf66e8 | 2026-07-04 |
| 3 | Stage-1 hard rules + POLICY.md parser | ✅ | 27635ba | 2026-07-04 |
| 4 | Scene engine + inference + policy table | ✅ | ebc6025 | 2026-07-04 |
| 5 | Judge interface + fixture backend + routing | ✅ | 7e4b053 | 2026-07-04 |
| 6 | Demo fixture + replay runner | ✅ | 8c28c73 | 2026-07-04 |
| 7 | Demo routing regression (full-table) | ✅ | be22ac9 | 2026-07-04 |
| 8 | Real LLM judge backends | ✅(mocked) | 0c96256 | 2026-07-04 |
| 9 | Stage-2 embedding classifier | ✅(mocked) | e51fe72 | 2026-07-04 |
| 10 | Delivery: terminal + desktop | ✅ | 96e90d6 | 2026-07-04 |
| 11 | Delivery: Telegram + feedback buttons | ✅(mocked) | d2a9013 | 2026-07-04 |
| 12 | Learner: signals, EMA, threshold tuning | ✅ | 822f574 | 2026-07-04 |
| 13 | Shadow mode + Tact Report | ✅ | b270bd6 | 2026-07-04 |
| 14 | Dispatch executors | ✅ | 71acdbf | 2026-07-04 |
| 15 | Dispatch verification | ✅ | 9008c96 | 2026-07-04 |
| 16 | Arrive-with-a-plan | ✅ | a445061 | 2026-07-04 |
| 17 | Memory: curate + associate | ✅(mocked) | ce5151b | 2026-07-04 |
| 18 | Ingest protocol: webhook + MCP | ✅ | a590ecd | 2026-07-04 |
| 19 | Built-in sources: GitHub + RSS | ✅ | c3f8a2b | 2026-07-04 |
| 20 | Onboarding wizard + service install | ✅ | b6f8508 | 2026-07-04 |
| 21 | Digest polish + nightly distillation | ✅ | 77285a4 | 2026-07-04 |
| 22 | OpenClaw skill | ✅(mocked) — merged into 29 | 907e77b | 2026-07-04 |
| 23 | Docs + README | ✅ | 1069048 | 2026-07-04 |
| 24 | Release assets | ✅ | ca02e21 | 2026-07-04 |
| 25 | Golden dataset + eval harness | ✅ | d34868b | 2026-07-05 |
| 26 | Decision trace + cost accounting | ✅ | 87f5d24 | 2026-07-05 |
| 27 | Prompt governance | ✅ | 5b23360 | 2026-07-05 |
| 28 | Failure injection + graceful degradation | ✅ | 07c8fc7 | 2026-07-05 |
| 29 | Dual skill packaging (absorbs 22) | ✅(mocked) | b7114a7 | 2026-07-05 |
| 30 | Upstream integration examples | ✅ | 8aa0501 | 2026-07-05 |
| 31 | README v2 — quantified first screen | ✅ | 896dc49 | 2026-07-05 |

## Final summary (2026-07-04)

All 24 steps complete, one commit per step, plus four hostile-review commits
(review(phase1..4)). 218 tests + ruff green on every commit; GitHub Actions CI
green on every push. `uvx --from . chief demo` delivers the offline
day-of-engineer replay end-to-end (24 events → 14 blocked · 6 batched ·
3 handled · interrupted exactly once), the full-table routing regression guards
it permanently, and `make release-check` runs the demo from the built v0.1.0
wheel.

Steps marked ✅(mocked) were built against mocks/cassettes because they need
human-only resources — live LLM API keys (8), torch disk space for real
embeddings (9, 17), a Telegram bot token (11), and a local OpenClaw install (22). PyPI is now published (v0.3.1, 2026-07-07). Details and the exact path to un-mock each one are
in BLOCKERS.md. Design decisions taken where the spec was ambiguous are
one-liners in docs/decisions.md (23 ADRs).

## Final summary — v3.1 amendment (2026-07-05)

Steps 25-31 complete, one commit per step, plus two hostile-review commits
(review(phase5) after Step 28, review(phase6) after Step 31). Steps 8-24 were
already ✅ from the v3 run (original Step 22 absorbed into Step 29). 265 tests
+ ruff green on every commit; `make release-check` re-verified from the built
wheel (`chief demo`, `chief eval`, and `chief lite` all run installed).

What v3.1 added: a 200-case golden dataset with a capability/regression-split
eval harness (`chief eval`, CI-gated at 100% on the demo 24); per-decision
tracing and USD cost accounting with explicit DeepSeek cache-hit/miss pricing
(`chief trace`); versioned Jinja2 prompt templates with eval-gated changes
(`chief eval --compare`); chaos-tested graceful degradation (judge down →
rules-only conservative routing, degraded=true, auto-recovery, surfaced in
`chief status`); dual skill packaging with a zero-daemon `chief lite` mode;
runnable upstream-integration examples; and a README whose first-screen
numbers regenerate via `make readme-metrics` (gated by
tests/test_readme_metrics.py).

Mocked pieces and their un-mock paths are in BLOCKERS.md (live-backend eval
numbers and prompt-compare diffs need an LLM key; live skill-host halves need
OpenClaw / a Claude Code session). New design decisions: 14 ADRs appended to
docs/decisions.md.

## v3.2 summary (2026-07-06)

Steps 32-36 complete: the product surface. Natural feedback
(should/shouldn't-interrupt, weighted above all inferred signals), a local
web console (Today/History/Rules/Tasks/Sources + 👍/👎 everywhere), a
connector framework with Composio as the flagship adapter (HMAC-verified
trigger webhooks; slots documented for zapier/n8n/MCP-push), one-click
`chief connect`, and v0.3.0 shipped through the automated release pipeline.
296 tests. Live Composio round-trip needs an account + tunnel (BLOCKERS.md).

## Step 38 — cohort preference-learning benchmark (2026-07-08)

Generalized the single-user reward-loop eval (Step 37) to a population. A
committed, seeded 100-user dataset (`eval/personas.jsonl`, reproducible from
`eval/generate_personas.py`) drives a train/eval-split benchmark
(`eval/cohort.py`, `chief eval --cohort`): ±1 feedback trains per persona,
interrupt precision/recall/F1 is scored on a disjoint held-out stream. The
report is a distribution — 64% of users converge (median 3 rounds), held-out
interrupt F1 0.10 → 0.81, a feedback-noise-tier breakdown — and it states the
provable ceiling (`s ≥ √(T/5)`; a user converges iff every wanted topic is
reachable, so `converged ∪ ceiling-capped == everyone`). 11 new tests pin the
numbers, dataset-vs-generator reproducibility, and the ceiling invariant.
326 tests. Write-up: `docs/eval/cohort-benchmark.md`.

## Step 39 — per-stage ablation eval (2026-07-13)

Proved the three-stage funnel (SPEC §4.4) is load-bearing, not architecture
theater. `eval/ablation.py` (`chief eval --ablation`) runs the golden 200 with
each stage disabled and reports accuracy + cost deltas, offline and
deterministic: full funnel 100% / 141 judge calls; −stage-1 (judge-only) 80% /
200 calls (+42% cost, −20 pp — the hard rules own state a stateless judge can't
see); −judge (rules-only degraded) 61.5% (the judge adds +38.5 pp of
discretion). Stage-2's similarity cache is measured on repeat traffic — its real
job — erasing all 141 judge calls on identical replay (199/200 routing
preserved). 9 tests pin the numbers and stage contracts; write-up in
`docs/eval/ablation.md`. 350 tests.

## Step 40 — calibration eval (2026-07-13)

Proved the single number Chief routes on is trustworthy. `eval/calibration.py`
(`chief eval --calibration`) is a view over the cohort's held-out stream — the
one offline classifier that makes real errors — so ~7.2k (score, wanted) pairs
with genuine mistakes are available. Headline: the raw salience score is
*anti*-correlated with preference (AUC 0.368, below chance — loud newsletters
unwanted, quiet incidents wanted) and learning *inverts* it to AUC 0.918.
Reliability is monotone; a parameter-free isotonic recalibration (fit on half,
scored on the held-out half) cuts ECE 0.263 → 0.011. Per-scene thresholds are
shown to be deliberate operating points (idle 83% recall → meeting 51%, precision
≥94% throughout). PersonaResult gained additive eval_scores_before/after so
cohort's pinned numbers are untouched. 9 tests; write-up in
`docs/eval/calibration.md`. 359 tests.
