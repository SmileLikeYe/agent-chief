# Skill packaging — manual test transcripts (Step 29)

Both skills ship the same contract: propose, then obey. The `chief lite`
transcripts below are real output (recorded 2026-07-05, v0.1.0 wheel); the
host-side halves need a live OpenClaw / Claude Code session (see BLOCKERS.md).

## claude-code host

Setup: copy `skills/claude-code/` into the project's `.claude/skills/`
directory (or reference it from CLAUDE.md), install Chief (`uvx agent-chief`).

Transcript (deterministic part, reproducible on any machine):

```console
$ chief lite '{"source":"claude-code-watcher","topic":"ops.heartbeat",
    "summary":"Heartbeat: all clear, nothing to report"}'
{"event_id":"evt_...","route":"drop","score":null,...,
 "matched_rules":["zero_information"],
 "reason":"zero-information report ...","stage":1,"degraded":false}

$ chief lite '{"source":"claude-code-watcher","topic":"dev.ci",
    "summary":"CI failed on main: test_auth_flow broken by PR #482"}'
{"event_id":"evt_...","route":"digest",...,"stage":3,"degraded":true,
 "reason":"judge unavailable (LookupError); conservative rules-only routing to digest"}
```

Expected host behavior, verified by reading the Decision:
noise never reaches the user; without an LLM key nothing can interrupt
(`degraded: true` ⇒ digest at most). With `[llm]` configured in
`~/.chief/config.toml` the second event scores normally.

## openclaw host

Setup per `skills/openclaw/SKILL.md`: agent calls the MCP `propose` tool
(server: `python -m ingest.mcp_server`); interrupts ride OpenClaw channels via
`~/.openclaw/outbox/*.json`; dispatched tasks arrive in `~/.openclaw/tasks/`.

The MCP round-trip is covered by automated tests (`tests/test_ingest.py` MCP
client tests; outbox/tasks file protocol in `tests/test_openclaw.py`). The
live-host halves (a real OpenClaw reading the outbox, a real Claude Code
session loading the skill) require installs this machine doesn't have —
tracked in BLOCKERS.md with exact un-mock steps.
