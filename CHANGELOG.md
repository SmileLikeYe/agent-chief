# Changelog

All notable changes to Chief are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[SemVer](https://semver.org) (0.x: minor bumps may break).

## [Unreleased]

## [0.8.0] — 2026-07-22

### Added
- **The outbound protocol** (SPEC §4.5, generalized): the exit is a protocol
  too. `chief connect webhook --url https://your-receiver/hook --secret …`
  turns **any HTTP receiver** — a phone-app bridge, an ntfy relay you host, a
  desktop applet, a home-automation hub — into a delivery channel by
  implementing one contract: a signed JSON POST of
  `{event_id, topic, summary, plan, level, sent_at}`. No bespoke adapter per
  app, and the §13 stance is unchanged (no team-chat adapters ship; this is
  neutral egress to *your* receiver).
  - The signature is byte-for-byte the svix scheme the Composio *inbound*
    connector already verifies (`v1,` + base64 HMAC-SHA256 over
    `"{event_id}.{timestamp}." + body`) — one verify function covers both
    directions, and a test proves the round-trip. Unsigned mode works but
    warns loudly: an unsigned receiver can't tell Chief from anyone who found
    its URL.
  - `--max-level` caps what Chief asks of the receiver; transient failures are
    retried 3× with backoff before the channel is considered down.
  - Docs: `docs/protocol.md` §4 (receiver contract + verify snippet + honest
    semantics).

### Fixed
- **Delivery walks a fallback chain instead of betting on one channel**: if
  the picked channel fails, `deliver()` tries the next
  (webhook down → Telegram → desktop → terminal) — degraded loudness beats a
  silent loss. Only when *every* channel fails does the loss surface in the
  log. Previously a single receiver outage silently dropped the interrupt.
  There is still no outbound queue; that limit is documented, not hidden.
- **Clean shutdown acks the handled Telegram batch**: cancelling the poll task
  fires one last offset-only `getUpdates` (2s hard timeout, never blocks
  daemon exit), so a restart no longer replays already-handled updates —
  no duplicate feedback rows, re-ingested pushes, or repeated bot replies.
  A crash still replays; the 24h dedup absorbs it.

## [0.7.0] — 2026-07-21

### Added
- **The push pipe** (SPEC §4.1, generalized): both ends of Chief-as-attention-router
  are now first-class, with no new endpoint and no new external dependency.
  - **Inbound as a one-liner**: `chief push "CI failed on main" --topic dev.ci
    --urgency high` (or `… | chief push` with full event JSON on stdin) is
    `POST /v1/events` as a CLI — any skill, script, or cron job pushes attention
    to the running daemon and gets back the one-line verdict
    (`interrupt · deep_work · score 4.2 — …`; `--json` for the full Decision).
    The minimal contract is `ingest.push.push_payload` — just `{source, summary}`,
    validated at the edge: empty summary / unknown urgency fail fast with a human
    error, summaries collapse to one line and clamp to the schema limit.
  - **Telegram is now a two-way pipe**: a message *to* the bot becomes a candidate
    event (the off-box inbound path for anything that can't reach `127.0.0.1`),
    and the bot replies with the decision — phone → Chief → phone. Accepted
    **only** from the configured `chat_id`; a stranger's message is dropped
    before ingest. Long/multiline messages keep their full text in `detail`.
  - Docs: `docs/protocol.md` §1b/§1c.

### Fixed
- The Telegram poll task now **outlives the network**: getUpdates failures
  (5xx/timeout/bad body) retry with capped exponential backoff (1s→60s) instead
  of silently killing the daemon's only phone pipe — a latent single point of
  death that predates this release (feedback buttons died with it too).
- A poison update costs exactly itself: the offset advances past the whole batch
  before handling, and a failing update is logged and skipped — never the rest
  of the batch, never the loop, never a redelivery storm.
- The decision-echo reply is best-effort: once the pipeline has decided and
  persisted, a failed send is logged, never propagated.

## [0.6.0] — 2026-07-19

### Added
- **Pin lifecycle** (SPEC §4.6, cohort-v3): learned interrupt pins are no longer
  write-only. An explicit `should_not_interrupt` on a pinned topic now **removes
  the pin immediately** ("stop flagging this") — symmetric to the
  saturation-driven escalation that created it, but responsive, since a pin
  forces an interrupt on *every* event of its topic. Pins also **decay**: each
  firing refreshes a `last_fired` clock (`State.touch_pin`), and the nightly job
  prunes any pin unused for `PIN_STALE_DAYS` (30), so the pin set can't grow
  unbounded and always reflects what the user still wants flagged. Pin records
  upgraded from a bare timestamp to `{pinned_at, last_fired}`; reads tolerate the
  legacy v2 string format so no pin is lost on upgrade. New `State.remove_pin` /
  `touch_pin` / `prune_stale_pins` + `core.learner.prune_stale_pins`. 5 tests.
- **Preference-drift eval** (`chief eval --drift`): flips every cohort user's
  preferences mid-stream and scores held-out interrupt F1 against the *current*
  truth — **0.86 (learned) → 0.69 (the instant it flips) → 0.88 (re-learned)**,
  91% of users recovering to within 0.05 of pre-drift quality. The subplot proves
  un-pinning at scale: of the 30 users whose dropped topic had been pinned, **100%
  had that pin removed**, so an over-learned interrupt never outlives the
  preference that created it. Writes `eval/reports/drift.md`; write-up in
  `docs/eval/drift.md`. 3 tests.

## [0.5.0] — 2026-07-13

### Added
- **Learned interrupt pins** (SPEC §4.6, cohort-v2): when a `should_interrupt`
  correction keeps arriving but the EMA weight step has all but stopped (the
  weights can't lift a quiet topic over the scene's interrupt bar), the learner
  escalates to a **hard per-topic pin**, and the brain routes that topic to
  interrupt like a stage-1 rule (no judge call). On the 100-user cohort this
  raises convergence from **64% → 95%** (rescuing 31 of 36 structurally-capped
  users; held-out F1 0.81 → 0.87), and the only users left are the noisiest — the
  residual ceiling is now noise-limited, not arithmetic. Surfaced in the console's
  `/api/learning`. `chief eval --cohort` reports the pin-inclusive numbers;
  `run_cohort(pins=False)` reproduces the EMA-only baseline.
- **Adversarial red-team suite** (`chief eval --redteam`, exits 1 on any breach):
  16 hostile payloads across 5 categories — guard bypass (injection can't
  override a mute/dedup/quiet-hours), persuasion-ignored (prose doesn't move the
  score), malformed-payload fail-closed, executor shell-escape (SPEC §13), and
  terminal-escape — **all contained**, offline and deterministic. Write-up in
  `docs/security/red-team.md`.

### Security
- **Terminal-escape / rich-markup injection fixed.** Untrusted event summaries
  were rendered into a rich `Panel` with markup enabled and raw ANSI passed
  through. Control bytes are now stripped at the delivery chokepoint
  (`delivery.base.strip_control`) and the terminal channel renders the body as
  `rich.text.Text` (markup shown literally, never interpreted).
- **Ingest now fails closed with 422.** A hostile/oversized field on `/v1/events`
  raised an unhandled `ValidationError` (500); `ingest/http.py` now returns 422.

### Added
- **Calibration eval** (`chief eval --calibration`): measures whether the routing
  score is a *trustworthy* decision variable, on the cohort's held-out stream (the
  one offline classifier that makes real errors). Headline: the raw salience score
  ranks **backwards** (AUC 0.368 — loud topics are the unwanted ones) and
  preference learning **inverts it to AUC 0.918**. Reliability is monotone; a
  parameter-free isotonic recalibration cuts ECE **0.263 → 0.011**; per-scene
  thresholds are shown to trade recall for precision as the bar rises (idle 83%
  recall → meeting 51%, precision ≥94% throughout). Writes
  `eval/reports/calibration.md`; write-up in `docs/eval/calibration.md`. 9 tests.
- **Ablation eval** (`chief eval --ablation`): turns each funnel stage off on the
  golden 200 and measures the accuracy **and** cost delta, so the three-stage
  architecture (SPEC §4.4) is proven load-bearing rather than asserted. Stage-1
  hard rules save **+42% of judge calls** and **+20 pp agreement** (state a
  stateless judge can't see); the judge lifts **+38.5 pp** over the rules-only
  degraded floor (61.5%); stage-2's similarity cache erases every judge call on
  repeat traffic (199/200 routing preserved). Deterministic/offline; writes
  `eval/reports/ablation.md`; write-up in `docs/eval/ablation.md`. 9 tests pin
  the figures and the stage contracts.

## [0.4.0] — 2026-07-10

### Added
- **Cohort preference-learning benchmark** (`chief eval --cohort`): the reward
  loop, run over a committed 100-user dataset (`eval/personas.jsonl`, seeded and
  reproducible) instead of one simulated user. Train/eval split — corrected by
  ±1 feedback during training, scored on a **held-out** event stream — reporting
  a distribution: **64% of users converge** (median 3 rounds), held-out interrupt
  **F1 0.10 → 0.81**, a noise-tier breakdown, and the provable ceiling
  (`converged ∪ ceiling-capped == everyone`). Writes `eval/reports/cohort.md`;
  write-up in `docs/eval/cohort-benchmark.md`. 11 tests pin the numbers, the
  dataset-vs-generator reproducibility, and the ceiling invariant.
- **Executable onboarding**: `chief token` prints the generated local webhook
  credential for scripts, and real-source setup now uses one persistent CLI path.
- **Release metadata guard**: tags must match `pyproject.toml` and the latest
  CHANGELOG version before release artifacts can build.

### Fixed
- Quiet hours, scene inference, digest delivery, and nightly jobs now use the
  user's local wall clock while persisted timestamps and rolling windows stay UTC.
- Re-running `chief init` preserves connectors, custom settings, and existing
  secrets instead of replacing the config with defaults.
- Chief home and credential files are written atomically with `0700` / `0600`
  permissions; new installs receive a random webhook bearer token.
- The resident fails fast for demo fixtures or a hosted judge without an API key,
  instead of claiming to be healthy and degrading only after the first event.
- Linux systemd and macOS launchd service generation are tested separately;
  GitHub Actions now runs all **341 tests** on both Ubuntu and macOS.

## [0.3.1] — 2026-07-06

Security & robustness hardening of the v0.3.0 product surface (from a
dedicated multi-agent review pass).

### Fixed
- **Console XSS → token theft** closed: event/task ids (attacker-shaped) now
  ride escaped `data-*` attributes with delegated listeners, never inline
  handlers.
- All API auth uses constant-time comparison (`hmac.compare_digest`); uvicorn
  binds `127.0.0.1` explicitly on both servers.
- **Composio webhook**: timestamp freshness (±5 min anti-replay), 1 MiB body
  cap before buffering, non-ASCII signature headers no longer 500, non-dict
  trigger data wrapped instead of crashing.
- Console task-approve honors `task.executor` (was hardcoded `claude_code` — an
  escalation over the query-only shell executor).
- History search runs in SQL, so matches beyond the newest rows are found.
- One `apply_feedback` path behind HTTP/MCP/Telegram/console: the natural
  should/shouldn't-interrupt signals now learn identically everywhere (MCP and
  Telegram previously only stored a raw row); unknown signals are rejected.
- `chief connect` backs up and refuses to rewrite configs its serializer can't
  round-trip, instead of corrupting them in place.

## [0.3.0] — 2026-07-06

The "product surface" release (SPEC v3.2, Steps 32–36): Chief for people, not
just for people who read specs.

### Added
- **Local web console** (`chief ui`, also served by `chief run`) at
  `127.0.0.1:8787/ui`: Today / History / Rules / Tasks / Sources views,
  POLICY.md editing that takes effect immediately, dispatch approve/reject
  (verification still enforced), and 👍/👎 on every decision. Single user,
  token-gated, one static HTML file — no cloud, no build toolchain.
- **Natural feedback**: `should_interrupt` / `should_not_interrupt` as
  first-class signals — stronger than every inferred signal — via the console,
  `POST /v1/feedback`, the MCP `feedback` tool, and new Telegram buttons.
- **Connector framework** with **Composio** as the flagship adapter:
  HMAC-verified trigger webhooks (`/v1/connectors/composio`) translate
  GitHub/Gmail/Slack/500+ app events into candidate events; documented slots
  for zapier/n8n and MCP-push agents.
- **One-click connect**: `chief connect composio|github|rss` edits config
  surgically and prints exact next steps; `chief sources` shows status.
- SPEC §13 revised by the owner: local-only console and connector ingest are
  in scope; the hosted-UI and chat-delivery bans stand.

## [0.2.0] — 2026-07-05

The "trust & distribution" release (SPEC v3.1, Steps 25–31) plus two
multi-agent review hardening passes.

### Added
- **Eval harness** (`chief eval`): a 200-case golden dataset with strictly
  separated CAPABILITY (improvable, report the number) and REGRESSION evals
  (the demo 24 — 100% forever, CI-gated); bucketed markdown reports by
  route/topic/scene.
- **Decision tracing + cost accounting** (`chief trace <event_id>`): per-stage
  latency, tokens in/out/cached, and USD cost on every decision, with
  per-model list prices (DeepSeek cache-hit vs cache-miss modeled explicitly).
  The Tact Report gained a cost dimension: % events reaching the LLM, cache
  hit rate, judgment spend — all windowed to the report period.
- **Prompt governance**: all prompts are versioned Jinja2 templates
  (`judge/templates/v1/`); the version is stamped into every judged decision's
  audit record, and `chief eval --compare v1 v2` produces an agreement-delta +
  flipped-samples diff. House rule: no prompt change merges without one.
- **Graceful degradation**: chaos-tested judge failures (malformed JSON,
  timeout, backend down) fall back to rules-only conservative routing — never
  interrupt while blind, never drop — marked `degraded=true`, auto-recovering,
  and surfaced in `chief status`.
- **`chief lite`**: zero-daemon judgment-only mode (stages 1–3 + routing) for
  one-shot callers and skills.
- **Dual skill packaging**: Claude Code skill alongside the OpenClaw skill.
- **Integration examples** (`examples/integrations/`): a stock-analysis-bot
  feed and a generic webhook template, both runnable offline.
- **Quantified README**: the first screen leads with numbers regenerated from
  the deterministic demo replay via `make readme-metrics`, gated by tests.
- Open-source scaffolding: LICENSE (MIT), CONTRIBUTING, CODE_OF_CONDUCT,
  SECURITY, issue/PR templates, examples/, bilingual README, `chief --version`.

### Fixed (highlights from the two review passes)
- Cost accounting: per-model pricing (default gpt-4o-mini configs were billed
  at gpt-4o rates, ~17×); failed retries and mid-retry transport errors are
  billed; a single `Decision.cost` source of truth.
- Robustness: `"usage": null` from OpenAI-compatible proxies no longer breaks
  judgments; the Brain's outer judge timeout (150s) now fits HTTPJudge's full
  retry budget; unknown `prompt_version` fails fast at startup; LLM-echoed
  `usage` keys are stripped before validation.
- Reserved-namespace hardening: the degradation marker moved to a dedicated
  `meta` table and externally supplied dunder topics are namespaced at ingest.
- Eval integrity: regression gates before the paid capability run; a broken
  fixture fails loud while a flaky backend degrades a single case instead of
  aborting a paid run; loud warning when "low agreement" is really an outage.

## [0.1.0] — 2026-07-04

Initial release: the full SPEC v3 implementation (Steps 1–24).

- Three-stage worthiness engine (hard rules → similarity classifier → LLM
  judge: ollama/deepseek/anthropic/openai, all optional) × scene engine with
  per-scene interrupt thresholds.
- Five routes: interrupt / digest / dispatch / curate / drop; dispatch
  verifies results before reporting ("done is a claim, not a proof") and
  arrives with a plan.
- Shadow mode (trust is earned), Tact Report, EMA learner with nightly
  human-readable POLICY.md distillation.
- Ingest protocol: webhook + MCP tools + GitHub/RSS pollers; delivery over
  terminal/desktop/Telegram with feedback buttons.
- Fully offline deterministic demo (`uvx agent-chief demo`) with a
  full-table routing regression.

[0.8.0]: https://github.com/SmileLikeYe/agent-chief/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/SmileLikeYe/agent-chief/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/SmileLikeYe/agent-chief/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/SmileLikeYe/agent-chief/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/SmileLikeYe/agent-chief/compare/v0.3.1...v0.4.0
[0.3.1]: https://github.com/SmileLikeYe/agent-chief/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/SmileLikeYe/agent-chief/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/SmileLikeYe/agent-chief/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/SmileLikeYe/agent-chief/releases/tag/v0.1.0
