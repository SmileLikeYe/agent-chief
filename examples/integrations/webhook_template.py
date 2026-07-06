"""Generic upstream template — copy this into any agent that wants to report.

Contract (docs/protocol.md): POST a candidate event, obey the Decision.
This template degrades gracefully through three transports:

1. resident Chief webhook (CHIEF_URL + CHIEF_TOKEN set, `chief run` running);
2. otherwise: in-process judgment (same pipeline `chief lite` uses) — offline,
   which is also what makes this template runnable end-to-end as a demo:

    python examples/integrations/webhook_template.py
"""

import asyncio
import json
import os

FIXTURE_EVENTS = [
    {"source": "my-agent", "topic": "ops.heartbeat",
     "summary": "Heartbeat: all clear, nothing to report"},
    {"source": "my-agent", "topic": "dev.ci",
     "summary": "CI failed on main: test_auth_flow broken by PR #482",
     "suggested_action": "revert #482 or fix the fixture",
     "claimed_urgency": "high"},
]


def propose_via_webhook(payload: dict) -> dict | None:
    """Transport 1: the resident daemon. Returns None if unreachable."""
    url, token = os.environ.get("CHIEF_URL"), os.environ.get("CHIEF_TOKEN")
    if not (url and token):
        return None
    try:
        import httpx

        resp = httpx.post(f"{url}/v1/events", json=payload, timeout=10,
                          headers={"Authorization": f"Bearer {token}"})
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None  # daemon down → fall through to in-process judgment


async def propose_in_process(payload: dict) -> dict:
    """Transport 2: judgment-only, no daemon — literally what `chief lite` runs."""
    from core.brain import judge_once

    return json.loads((await judge_once(payload)).model_dump_json())


def obey(decision: dict) -> None:
    """The whole point: whatever the route, an upstream agent does NOTHING
    user-facing. Chief owns delivery."""
    print(f"  Decision: route={decision['route']}"
          f"{' (degraded)' if decision.get('degraded') else ''} — {decision['reason'][:70]}")


async def main() -> None:
    for payload in FIXTURE_EVENTS:
        print(f"→ proposing: {payload['summary'][:70]}")
        decision = propose_via_webhook(payload) or await propose_in_process(payload)
        obey(decision)


if __name__ == "__main__":
    asyncio.run(main())
