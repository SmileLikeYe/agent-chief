---
name: chief-gatekeeper
description: Route everything noteworthy through Chief instead of messaging the user. Use whenever a heartbeat, watcher, or background task finds something it wants to tell the human.
---

# Chief is the gatekeeper of the user's attention

You (an OpenClaw agent) **MUST NOT message the user directly** when a heartbeat
or background check finds something noteworthy. The user has appointed Chief as
their chief of staff; going around it is a protocol violation.

## What to do instead

1. Call Chief's MCP tool `propose` with a candidate event:

```json
{
  "source": "openclaw-heartbeat",
  "topic": "dev.ci",
  "summary": "CI failed on main: test_auth_flow broken by PR #482",
  "detail": "pytest output attached",
  "suggested_action": "fix the failing test",
  "evidence": ["https://github.com/acme/repo/actions/runs/9"],
  "claimed_urgency": "high"
}
```

2. **Obey the returned Decision.** Its `route` field is final:
   - `interrupt` / `dispatch` — Chief handles delivery and any prep work. Do nothing.
   - `digest` — the item will appear in the next digest. Do nothing.
   - `curate` — Chief remembered it. Do nothing.
   - `drop` — it was noise. Definitely do nothing. Do not retry with louder wording.

3. Never send "all clear / nothing to report" messages at all. Chief drops them,
   and each one you send erodes the user's trust in every future message.

## Chief MCP connection

Run the server: `python -m ingest.mcp_server` (stdio), or point your MCP client
at the resident `chief run` process. Tools available: `propose`, `feedback`,
`digest`, `policy`, `stats`.

## Delivery callback (interrupts ride OpenClaw's channels)

Chief writes outbound messages as JSON files into `~/.openclaw/outbox/`
(`skills/openclaw/hook.py:OpenClawChannel`). Each file:

```json
{"origin": "chief", "event_id": "evt_...", "topic": "...", "text": "...", "silent": true}
```

Deliver `text` through the user's existing OpenClaw channel; honor `silent`.
Task injection works the same way in reverse: Chief drops
`{"origin": "chief", "task_id": ..., "goal": ..., "acceptance": ...}` into
`~/.openclaw/tasks/` when it dispatches work to OpenClaw (executor=openclaw).
Report results back via the `feedback` tool (`task_ok` / `task_fail`).
