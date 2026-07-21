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

## Step 41 — adversarial red-team suite (2026-07-13)

Earned the trust-boundary claim with attacks, not assertions. `eval/redteam.py`
(`chief eval --redteam`, exits 1 on any breach) runs 16 hostile payloads across 5
categories — guard bypass, persuasion-ignored, malformed payloads, executor
shell-escape (§13), terminal-escape — all contained, offline and deterministic.
Writing it surfaced and closed two real gaps: terminal delivery rendered
untrusted summaries with rich markup enabled and passed raw ANSI (fixed:
`delivery.base.strip_control` + `rich.text.Text` in the terminal channel), and
`/v1/events` let a hostile/oversized field escape as an unhandled 500 (fixed: a
`ValidationError`→422 handler in `ingest/http.py`). 12 tests (harness + HTTP
413/401/422 + terminal rendering); write-up in `docs/security/red-team.md`.
370 tests.

## Step 42 — cohort v2: learned interrupt pins (2026-07-13)

Broke the 36% structural ceiling from Step 38. EMA weights only pull toward an
event's components, so a wanted-but-quiet topic converges below its scene's
interrupt bar and stays there. New escalation (`core.learner`): when a
should_interrupt correction arrives but the weight step < 0.01 (saturated), write
a hard per-topic pin (`State.add_pin`, stored in meta); `core.brain` consults it
right after stage-1 and forces interrupt like a policy rule, no judge call. Pins
only escalate from should_interrupt, so they lift only *wanted* topics —
precision preserved, §13 intact (content-blind, one-topic, no ML). Cohort
convergence 64% → 95% (31/36 structurally-capped users rescued, held-out F1
0.81 → 0.87); the 5 who remain are all erratic-noise — the residual ceiling is
noise-limited, not arithmetic. `run_cohort(pins=False)` reproduces the EMA-only
baseline; calibration runs pins=False to stay decoupled. Surfaced in
`/api/learning`. 3 new pin tests + updated cohort tests. 374 tests.

## Step 43 — pin lifecycle: un-pinning + decay (2026-07-19)

Made learned pins two-directional and self-maintaining, closing the write-only
gap from Step 42. An explicit `should_not_interrupt` on a pinned topic now removes
the pin on the first signal (`core.learner` → `State.remove_pin`) — responsive by
design, since a pin forces an interrupt on every event of its topic; a soft
`dismissed_fast` still only decays weights and never tears down a hard pin.
Creation stays saturation-gated (asymmetric on purpose: a single loud event can't
mint a pin). Decay: each firing refreshes `last_fired` (`core.brain` →
`State.touch_pin`) and the 03:00 job prunes pins idle > `PIN_STALE_DAYS` (30,
`core.learner.prune_stale_pins`), so the meta blob can't grow unbounded. Pin
records upgraded bare-ISO-string → `{pinned_at, last_fired}`; reads normalise via
`State._pin_entry` so v2 pins survive the upgrade. 5 new pin tests.

Evaluated, not asserted: a new **preference-drift benchmark** (`eval/drift.py`,
`chief eval --drift`) flips every cohort user's preferences mid-stream and scores
held-out interrupt F1 against the *current* truth — 0.86 (learned) → 0.69 (the
instant it flips) → 0.88 (re-learned), 91% recovering to within 0.05 of pre-drift.
The subplot proves un-pinning at scale: of the 30 users whose dropped topic had
been pinned, 100% had that pin removed. Reuses the cohort personas + production
primitives; deterministic/offline. 3 tests; write-up `docs/eval/drift.md`. 382 tests.

## Step 44 — the push pipe: attention in, notification out (2026-07-21)

Made both ends of Chief-as-attention-router first-class, without a new endpoint
or a new external dependency. Inbound: `chief push "…" --topic … --urgency …`
(and `… | chief push` for JSON) is the webhook as a one-liner — any skill,
script, or cron job pushes attention and gets back the one-line verdict;
`ingest.push.push_payload` is the minimal `{source, summary}` contract both it
and the Telegram relay produce, feeding the same `brain.process` funnel
(`push_to_daemon` → the running daemon, so pushes get persistence + delivery).
Off-box reachability + outbound reuse the already-trusted Telegram channel:
`poll_callbacks(process=…)` now turns a message *to* the bot into a candidate
event (gated to the configured `chat_id` — a stranger's message is dropped
before ingest, never processed) and replies with the decision, so the loop is
phone → Chief → phone. §13's delivery-surface list is untouched (personal
device, not a team channel; no ntfy/Pushover/cloud relay added). 11 new tests
(push envelope/render/round-trip/dedup, Telegram inbound + chat-gating);
docs in `docs/protocol.md §1b/§1c`. 393 tests.

Hostile-review hardening (same day): the poll task now outlives the network
(getUpdates failures back off 1s→60s instead of killing the daemon's only phone
pipe), a poison update costs exactly itself (offset advances past the batch
first; failures are logged and skipped), and the decision-echo reply is
best-effort (a failed send never propagates past a persisted decision).
Push-contract validation moved to the edge (`push_payload` raises on empty
summary / unknown urgency with a human message, pre-network), summaries
collapse to one line, and clamped/collapsed Telegram text keeps its full
original in `detail` — clamping is rendering, never data loss. CLI failure
modes are all explicit: non-object stdin JSON, unreachable daemon (any
transport error, not just refused), and 401 with a `chief token` hint. 8 new
tests pin every one of these. 401 tests.

## Step 45 — outbound protocol: any receiver becomes a channel (2026-07-21)

Applied "protocol, not pipes" to the exit. Instead of growing an adapter per
notification app, `delivery/webhook.py::WebhookChannel` POSTs one signed JSON
shape — `{event_id, topic, summary, plan, level, sent_at}` — to a URL the user
configures (`chief connect webhook --url … --secret …`, stored as
`[delivery.webhook]`), so a phone-app bridge, a self-hosted ntfy relay, or a
desktop applet becomes a delivery channel by implementing one receiver. The
signature is the same svix scheme the Composio inbound connector verifies
(a test round-trips `sign()` through the inbound `verify_signature` — one
verify function, both directions). §13 unchanged: no team-chat adapters, no
outbound queue pretending to exist (3 retries → raise → logged loss, docs say
so). `--max-level` caps how loud Chief may ask the receiver to be; control
characters are stripped before the wire. Inbound side: the claude-code skill
now teaches `chief push` (full pipeline) before `chief lite` (zero-daemon
fallback). 12 new tests (contract shape, signature symmetry, unsigned warning,
retry/raise, config wiring, connect CLI, skill ordering); receiver contract
documented in `docs/protocol.md §4`. 413 tests.

Reliability pass (same day): `deliver()` now walks a **fallback chain** instead
of betting the event on one channel — if the picked channel's send fails
(webhook receiver down, Telegram 5xx), the next channel gets it, and only an
all-channels failure propagates: a worthy event lands *somewhere*, degraded
loudness beats a silent loss. Inbound twin: cancelling the Telegram poll task
fires one last offset-only ack (2s hard timeout) so a clean daemon shutdown
never causes Telegram to replay the already-handled batch on restart. 5 new
tests (chain order, fallback-on-failure, all-fail raises, primary-unchanged,
shutdown ack). 418 tests.
