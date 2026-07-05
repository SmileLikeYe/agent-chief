"""How a heartbeat agent should report through Chief.

Run a check every N minutes, report *whatever you found* — Chief decides
whether anyone hears about it. The two payloads below show the contrast:

- the empty report is dropped by stage-1 (zero-information rule, µs, no LLM
  call) — the user never sees it, and that is the feature;
- the real finding carries suggested_action + evidence, scores well on
  actionability/confidence, and actually reaches the user.
"""

from python_client import ChiefClient

chief = ChiefClient()

# 1. Nothing happened. Report it anyway — Chief eats it, not the user.
empty = chief.propose(
    source="disk-watcher",
    topic="infra.disk",
    summary="Nightly disk check complete, all good.",
)
print(f"empty report  -> {empty['route']:9}  ({empty['reason']})")

# 2. Something happened. Same channel, same shape — different fate.
finding = chief.propose(
    source="disk-watcher",
    topic="infra.disk",
    summary="/var is at 91% and grew 6% in 24h; projected full in ~4 days",
    suggested_action="prune docker images or extend the volume",
    evidence=["/var/log/disk-watcher/2026-07-04.json"],
    claimed_urgency="medium",
)
print(f"real finding  -> {finding['route']:9}  ({finding['reason']})")
