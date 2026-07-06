# Architecture

```
sources/agents ──▶ Ingest ──▶ Brain Loop ──┬─▶ 🔔 Interrupt (with a plan)
 (webhook/MCP/built-ins)  (triage→associate→decide) ├─▶ 🤖 Dispatch (verify, then report)
                                ▲                   └─▶ 📚 Curate (memory)
                                │                            │
                     Scene Engine + Memory ◀─────────────────┘ (recalled by future events)
                                ▲
                     Feedback loop (user reactions / dispatch results)
```

One resident process (`chief run`) = one async event loop + scheduled jobs.
Everything is local: SQLite (`~/.chief/state.db`), markdown policy
(`~/.chief/POLICY.md`), JSONL audit log.

## The path of one event

1. **Ingest** (`ingest/`) — webhook `POST /v1/events`, MCP `propose`, or a
   built-in poller (GitHub notifications, RSS). Normalization stamps an id,
   fills `dedup_key`, infers a missing topic. Sources never judge.
2. **Triage** (`core/brain.py`) — 24h dedup; same-topic near-duplicates within
   10 min merge into the earlier event.
3. **Associate** (`memory/`) — top-3 memory hits by embedding cosine (> 0.78)
   are injected into the decision context and boost relevance ×1.2.
4. **Decide** (`core/scorer.py`) — three stages, cheapest first:
   - **Stage 1, hard rules (µs)**: muted topics, dedup, zero-information
     templates → drop; quiet hours (minus night whitelist) → digest;
     user rules in POLICY.md → direct route.
   - **Stage 2, similarity classifier (ms)**: looks-like-things-you-dismissed
     (>0.88, no engaged record) → drop; looks-like-things-you-engaged → route
     by history, no LLM call.
   - **Stage 3, LLM judge**: pluggable backend scores five dimensions
     (urgency, relevance, actionability, novelty, confidence);
     `score = Σ(w_topic·comp) − scene_cost`, routed against the scene's
     interrupt threshold. Judge output also flags `dispatchable` prep work
     and `memorize` facts.
5. **Act** — interrupts deliver at the highest level the scene allows
   (`delivery/`: terminal < desktop < telegram silent < ring). Dispatchable
   work runs FIRST (`dispatch/`), is verified (acceptance command or LLM
   second opinion, retry once, then ask the human), and the result rides along
   as the plan. 10-minute dispatch timeout — delivery never blocks.
6. **Learn** (`core/learner.py`) — button presses and dispatch results update
   per-topic EMA weights, engaged/dismissed sets, and a bounded global
   threshold. Nightly at 03:00 the day's changes distill into one
   human-readable POLICY.md line; memory TTL expiry runs in the same job.

## Scene engine (`context/`)

Pluggable `ContextProvider`s (clock, calendar today; focus/lock/activity
designed-in) merge signals; pure inference rules map them to one of 7 scenes
with a confidence. Confidence < 0.6 degrades interrupt → digest — the
asymmetry principle: a false interrupt costs more trust than a missed one.

## Trust ladder

New installs start in **shadow mode**: interrupts degrade to annotated digest
entries with ✓/✗ grading until 7 days pass or 50 samples accumulate. `chief
report` renders the Tact Report at any time.

## Accountability layer (v3.1)

Judgment is a claim too, so v3.1 makes it inspectable end to end:

- **Trace + cost** — every Decision records per-stage latency, tokens
  (cache-aware), and USD cost at per-model list prices (`judge/pricing.py`);
  `chief trace <event_id>` replays the whole chain. The Tact Report adds
  %-events-reaching-the-LLM, cache hit rate, and spend for its window.
- **Eval harness** (`eval/`) — a 200-case golden dataset. CAPABILITY evals
  measure the judge and may move; REGRESSION evals (the demo 24) are pinned
  at 100% in CI. `chief eval [--backend X]` writes bucketed markdown reports.
- **Prompt governance** — prompts are versioned Jinja2 templates
  (`judge/templates/<v>/`); the version is stamped into every audit record,
  and `chief eval --compare v1 v2` produces the flipped-samples diff that any
  prompt change must carry (CONTRIBUTING.md).
- **Graceful degradation** — if the judge backend fails (malformed output,
  timeout, down), routing falls back to rules-only conservatism: whatever
  passes stage 1 goes to digest — never interrupt while blind, never drop —
  flagged `degraded=true`, auto-recovering, visible in `chief status`.
- **`chief lite`** — the same Brain against an in-memory state for one-shot
  judgment-only callers (what the Claude Code / OpenClaw skills invoke);
  zero-config safety comes from the degradation path, not a second pipeline.

## Module map

| dir | role |
|---|---|
| `cli/` | typer CLI, wizard, resident-process assembly |
| `core/` | schema, state, brain loop, 3-stage scorer, learner, digest, policy |
| `context/` | scene providers + inference + scene policy table |
| `judge/` | LLM backends (ollama/deepseek/anthropic/openai/fixtures) + all prompts |
| `ingest/` | webhook, MCP server, normalization, github/rss pollers |
| `dispatch/` | executors (claude_code, whitelisted shell, openclaw) + verification |
| `memory/` | memory store, TTL/archive, association |
| `delivery/` | level abstraction + terminal/desktop/telegram channels |
| `demo/` | offline day-of-engineer replay (the 60-second wow) |
| `eval/` | golden dataset, capability/regression eval runner, prompt compare |
| `skills/` | claude-code + openclaw SKILL.md packaging (propose-and-obey) |
