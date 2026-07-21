# The Chief Ingest Protocol

How to connect *anything* — an agent, a cron job, a watcher, a webhook — to
Chief. This document is self-contained: you can build a working source from it
without reading Chief's code.

Chief does not build pipes. It defines this protocol; your source connects itself.

## The contract in one sentence

You POST a **candidate event**; Chief answers with a **Decision**; you obey it
(usually by doing nothing — that's the point).

## 1. HTTP webhook

```
POST http://<chief-host>:8787/v1/events
Authorization: Bearer <token from ~/.chief/config.toml [ingest].webhook_token>
Content-Type: application/json
```

### Request body (candidate event)

| field | type | required | meaning |
|---|---|---|---|
| `source` | string | ✅ | who you are, e.g. `"flight-watcher"` |
| `summary` | string ≤200 chars | ✅ | one line a human could act on |
| `topic` | string | recommended | hierarchical, e.g. `"travel.flight_change"`; the unit of learning. Omit and Chief infers one |
| `detail` | string | – | longer context |
| `suggested_action` | string | – | what the user could do right now (drives actionability) |
| `evidence` | string[] | – | URLs or local paths backing the claim (drives confidence) |
| `claimed_urgency` | `"low" \| "medium" \| "high"` | – | advisory only; Chief never trusts it blindly |
| `expires_at` | ISO datetime | – | when this stops being worth delivering |
| `dedup_key` | string | – | stable key for repeat sends; defaults to a hash of `summary` |

Minimal working example:

```bash
export CHIEF_TOKEN="$(chief token)"
curl -X POST http://localhost:8787/v1/events \
  -H "Authorization: Bearer $CHIEF_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "source": "my-agent",
    "topic": "dev.ci",
    "summary": "CI failed on main: test_auth_flow broken by PR #482",
    "suggested_action": "revert #482 or fix the fixture",
    "evidence": ["https://github.com/acme/repo/actions/runs/9"],
    "claimed_urgency": "high"
  }'
```

### Response (Decision, HTTP 200)

```json
{
  "event_id": "evt_20260706_1040_ab12",
  "route": "dispatch",
  "score": 0.87,
  "components": {"urgency": 0.9, "relevance": 0.9, "actionability": 0.85,
                  "novelty": 0.8, "confidence": 0.9},
  "scene": "deep_work",
  "scene_confidence": 0.75,
  "cost": 0.0,
  "matched_rules": [],
  "reason": "score 0.87 ≥ deep_work threshold 0.85; dispatchable prep work available",
  "stage": 3,
  "dispatch_task_id": "task_evt_20260706_1040_ab12"
}
```

`route` is final:

| route | what Chief does | what YOU do |
|---|---|---|
| `interrupt` | delivers to the user, scene-capped | nothing |
| `digest` | batches into the next digest | nothing |
| `dispatch` | runs prep work, verifies, then delivers with a plan | nothing |
| `curate` | stores a memory for future association | nothing |
| `drop` | nothing — it was noise | nothing. **Do not retry louder.** |

Errors: `401` bad token · `422` malformed event (fix your payload).

## 1b. `chief push` — the webhook as a one-liner

You don't have to hand-roll the HTTP call. Any local script, cron job, or skill
can push attention in one line:

```bash
chief push "CI failed on main" --topic dev.ci --urgency high
echo '{"source":"deployer","summary":"prod deploy finished"}' | chief push
```

`chief push` reaches the running daemon's `POST /v1/events` with the token from
your config (so `chief run` must be up) and prints Chief's one-line verdict —
`interrupt · deep_work · score 4.2 — production incident`. The minimal contract
is just `summary`; `--source`, `--topic`, `--urgency`, `--detail`, `--action`
are optional, and `--json` prints the full Decision. It is the inbound pipe: you
push, Chief decides, you obey (usually by doing nothing). For a zero-daemon
judgment with no persistence or delivery, use `chief lite` instead.

## 1c. Telegram — push from your phone

If you've wired a Telegram bot (`[delivery] telegram_token` + `chat_id`), it is
a two-way pipe: Chief pushes worthy events *to* your phone, and any message you
send *to* the bot becomes a candidate event — the off-box inbound path for
sources that can't reach `127.0.0.1`. Messages are accepted **only** from the
configured `chat_id` (a bot is reachable by anyone who finds it; a stranger's
message is dropped, never ingested), and the bot replies with the decision.

## 2. MCP

Chief exposes an MCP server (`python -m ingest.mcp_server`, stdio) with tools:

- `propose(event) -> Decision` — same contract as the webhook
- `feedback(event_id, signal)` — report reactions/results: `acted`, `read`,
  `dismissed_fast`, `muted`, `task_ok`, `task_fail`
- `digest(now=False)` — digest queue status
- `policy(action, text?)` — read (`show`) or append (`edit`) POLICY.md
- `stats(days=7)` — tact-report counters

## 2b. Feedback — teach Chief your preferences

```
POST http://<chief-host>:8787/v1/feedback
Authorization: Bearer <token>
{"event_id": "evt_...", "signal": "should_not_interrupt"}
```

Signals (strongest first): **`should_interrupt`** / **`should_not_interrupt`**
(natural feedback — "this deserved my attention" / "this didn't"), then
`acted`, `read`, `dismissed_fast`, `muted`, `task_ok`, `task_fail`. Known but
unroutable events still record the signal (`{"learned": false}`); unknown
signals get `422`. MCP agents use the `feedback` tool; the console and
Telegram expose 👍/👎 buttons that post the two natural signals.

## 2c. Connectors — out-of-the-box sources

Chief ingests from any [Composio](https://composio.dev) trigger:

```
POST http://<chief-host>:8787/v1/connectors/composio
webhook-id / webhook-timestamp / webhook-signature   (svix-style HMAC)
```

The v3 envelope (`{id, metadata:{trigger_slug,...}, data, timestamp}`) is
HMAC-verified against `[connectors.composio].webhook_secret`, replay-checked
(±5 min), and translated into a candidate event (`trigger_slug` → topic
family). Wire it with `chief connect composio --secret whsec_…`. The
connector registry documents open slots for zapier/n8n and MCP-push agents.

## 3. Rules of good citizenship

1. **Never send empty reports.** "All clear / nothing new / check complete"
   gets dropped, and it trains the user to ignore your source.
2. **One event per fact.** Send bursts and Chief will dedup (24h) and merge
   near-duplicates (10-min window) anyway.
3. **`claimed_urgency` is a hint, not a lever.** Inflating it is the fastest
   way to teach Chief's learner to discount your topic.
4. **Fill `suggested_action` and `evidence`.** Actionability and verifiable
   evidence are two of the five scoring dimensions — they are how good events win.
