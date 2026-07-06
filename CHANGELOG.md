# Changelog

All notable changes to Chief are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[SemVer](https://semver.org) (0.x: minor bumps may break).

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

[0.3.1]: https://github.com/SmileLikeYe/agent-chief/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/SmileLikeYe/agent-chief/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/SmileLikeYe/agent-chief/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/SmileLikeYe/agent-chief/releases/tag/v0.1.0
