---
name: chief-gatekeeper
description: Route everything noteworthy through Chief instead of interrupting the user. Use whenever a background task, watcher, cron job, or long-running session finds something it wants to surface to the human.
---

# Chief is the gatekeeper of the user's attention

You (a Claude Code agent or hook) **MUST NOT interrupt the user directly**
when background work finds something noteworthy. The user has appointed Chief
as their chief of staff; going around it is a protocol violation.

## What to do instead

Propose a candidate event and obey the Decision. Three transports — prefer the
first that works:

### 1. `chief push` — the running Chief (preferred)

```bash
chief push "CI failed on main: test_auth_flow broken by PR #482" \
  --source claude-code-watcher --topic dev.ci --urgency high \
  --action "revert #482 or fix the fixture"
```

One line in, one-line verdict out (`--json` for the full Decision). This is the
full pipeline: the event is persisted, feedback can teach Chief about it later,
and a worthy event is actually delivered (phone included). If it prints "can't
reach chief", the daemon isn't running — fall through to `chief lite`.

### 2. `chief lite` — zero-daemon judgment (fallback)

```bash
chief lite '{
  "source": "claude-code-watcher",
  "topic": "dev.ci",
  "summary": "CI failed on main: test_auth_flow broken by PR #482",
  "suggested_action": "revert #482 or fix the fixture",
  "evidence": ["https://github.com/acme/repo/actions/runs/9"],
  "claimed_urgency": "high"
}'
```

Prints a Decision as JSON: `route`, `score`, `reason`, `degraded`. Judgment
only — stages 1–3 + routing; no learner, no delivery daemon, no state. With no
LLM backend configured it is deliberately conservative: rules still fire
(noise still drops), everything else routes to `digest` with
`"degraded": true`.

### 3. Raw transports (webhook or MCP)

If you can't shell out: `POST http://localhost:8787/v1/events` with the
bearer token from `~/.chief/config.toml`, or the MCP tool `propose`
(server: `python -m ingest.mcp_server`, stdio).

## Obey the returned Decision — its `route` is final

- `interrupt` / `dispatch` — Chief handles delivery and any prep work. Do nothing.
- `digest` — it will appear in the next digest. Do nothing.
- `curate` — Chief remembered it. Do nothing.
- `drop` — it was noise. Definitely do nothing. Do not retry with louder wording.

## Rules of good citizenship

1. Never send "all clear / nothing to report" events. Chief drops them, and
   each one erodes the user's trust in every future message.
2. One event per fact; Chief dedups (24h) and merges near-duplicates anyway.
3. `claimed_urgency` is a hint, not a lever — inflating it teaches Chief's
   learner to discount your topic.
4. Fill `suggested_action` and `evidence`; they drive two of the five scoring
   dimensions.
