# Changelog

All notable changes to Chief are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[SemVer](https://semver.org) (0.x: minor bumps may break).

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

[0.2.0]: https://github.com/SmileLikeYe/agent-chief/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/SmileLikeYe/agent-chief/releases/tag/v0.1.0
