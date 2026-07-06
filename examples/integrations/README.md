# Upstream integrations — Chief as the judgment layer

The ecosystem position: **noisy upstream agents in, one accountable judgment
layer in the middle, a protected human on the other side.** Upstream bots
report *everything they notice*; Chief decides what deserves attention. The
bots never message the user.

Both examples run fully offline on fixture data and print visible Decisions:

```bash
python examples/integrations/stock_analysis_bot.py
python examples/integrations/webhook_template.py
```

## `stock_analysis_bot.py` — a daily_stock_analysis-style feed

Eight analyst-bot reports flow in (`stock_feed.json`): five are ritual noise
("daily check complete, all good"), three carry real information (a pre-market
drop, an earnings date, a dividend). End-to-end flow:

1. each report is proposed to Chief in-process (no daemon needed);
2. stage-1 rules kill the zero-information reports in microseconds — no LLM
   call, no cost;
3. the real findings route onward — with an LLM backend configured they are
   scored on five dimensions; with none they land in the digest marked
   `degraded=true` (conservative: never interrupt while blind, never drop).

## `webhook_template.py` — copy this into any agent

The generic shape every upstream source follows, with graceful transport
fallback: resident webhook (`CHIEF_URL`/`CHIEF_TOKEN`) when Chief is running,
in-process judgment otherwise. The `obey()` function is deliberately boring —
that is the contract: **whatever the route, the upstream agent does nothing
user-facing.**

Full protocol (fields, responses, good-citizenship rules):
[../../docs/protocol.md](../../docs/protocol.md).
