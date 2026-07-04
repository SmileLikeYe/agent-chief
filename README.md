# Chief

> **Your agents don't need more power. They need a chief of staff.**

Chief sits between you and everything that wants your attention — agents,
heartbeats, CI, RSS, watchers. Everything flows into it; it thinks for itself;
then it does exactly one of three things:

1. 🔔 **Interrupt** you — only when worth it, at the right moment, *arriving with a plan*.
2. 🤖 **Dispatch** work to your agents — and verify the result before reporting ("done" is a claim, not a proof).
3. 📚 **Curate** into memory — facts and intents not worth mentioning now, waiting to be connected later.

![demo](docs/assets/demo.gif)
*(demo GIF — see `make demo-gif`)*

## 60-second quickstart

```bash
uvx agent-chief demo        # zero keys, zero config, fully offline
```

You'll watch a day of an engineer's life replay: 24 events in → 14 blocked ·
6 batched · 3 handled (all verified) · **interrupted exactly once**.

Ready for real sources?

```bash
uvx agent-chief init        # 60s wizard, every question skippable
chief run                   # the resident brain
```

## Kill the "all clear" reports

If you run heartbeat agents, you know the ritual: *"All clear, nothing to
report."* Every few hours. Forever. Each one costs a glance, and the glances
add up until you stop reading — including the one that mattered.

Chief drops zero-information reports on the floor (regex **and** embedding
similarity against a canned empty-report set, both required — a security scan
that *mentions* "all clear" still gets through). The demo opens and closes with
this, because it's the single most requested feature among heartbeat users.

## Shadow mode: trust is earned

For its first 7 days (or 50 graded samples), Chief **never actually interrupts
you**. Would-be interrupts land in the digest annotated
`⚡ would have: interrupted you (score 0.87, scene deep_work)` with ✓/✗ grading
buttons. You watch it think, grade its calls, and only when it graduates does it
earn the right to ring. Graduation comes with a **Tact Report** (`chief report`).

## How it decides

Two axes, never one: **content worthiness × scene tolerance**.

- A three-stage worthiness engine: hard rules (µs) → similarity classifier (ms)
  → LLM judge (pluggable: Ollama local, DeepSeek, Anthropic, OpenAI).
- A scene engine (clock, calendar, focus, lock state — pluggable providers)
  with per-scene interrupt thresholds; low-confidence scenes degrade toward silence.
- Every learned preference distills nightly into a **human-readable
  [`POLICY.md`](policy/POLICY.template.md)** you can read and edit; your edits
  win, effective immediately.

## Connect your agent (3 lines)

```bash
curl -X POST http://localhost:8787/v1/events \
  -H "Authorization: Bearer $CHIEF_TOKEN" -H "Content-Type: application/json" \
  -d '{"source":"my-agent","topic":"dev.ci","summary":"CI failed on main"}'
```

Chief answers with a Decision — route, score, and a one-line reason. MCP agents
use the `propose` tool instead. Full contract: **[docs/protocol.md](docs/protocol.md)**.

## Going deeper

- [docs/protocol.md](docs/protocol.md) — the ingest protocol (connect anything in minutes)
- [docs/architecture.md](docs/architecture.md) — how the brain loop fits together
- [skills/openclaw/SKILL.md](skills/openclaw/SKILL.md) — make OpenClaw agents route through Chief
- [SPEC.md](SPEC.md) — the full implementation spec · [PROGRESS.md](PROGRESS.md) — build log

## Showcase

1. **Three events, three fates** — the hero GIF: an empty heartbeat (dropped), a
   CI failure (dispatched, fixed, verified), a delayed flight in a meeting
   (silent push, with rebooking options attached).
2. **The association chain** — event #5 plants "watch XX's next SDK release";
   event #19 recalls it and the evening digest connects the dots.
3. **Done is a claim, not a proof** — dispatch verification catching an agent
   that said "fixed" when it wasn't.

Local-first: one SQLite file + markdown under `~/.chief`. No cloud, no
telemetry, no web UI. MIT.
