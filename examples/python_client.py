"""A tiny Chief client: propose an event, obey the route, report feedback.

Usage:
    CHIEF_TOKEN=... python examples/python_client.py

The contract (docs/protocol.md): you POST a candidate event; Chief answers
with a Decision; you obey it — usually by doing nothing. That's the point.
"""

import os

import httpx

CHIEF_URL = os.environ.get("CHIEF_URL", "http://localhost:8787")
CHIEF_TOKEN = os.environ.get("CHIEF_TOKEN", "")


class ChiefClient:
    def __init__(self, url: str = CHIEF_URL, token: str = CHIEF_TOKEN):
        if not token:
            raise ValueError("set CHIEF_TOKEN first: export CHIEF_TOKEN=\"$(chief token)\"")
        self._http = httpx.Client(
            base_url=url, headers={"Authorization": f"Bearer {token}"}, timeout=10
        )

    def propose(self, **event) -> dict:
        """POST a candidate event; returns the Decision (route, score, reason)."""
        resp = self._http.post("/v1/events", json=event)
        resp.raise_for_status()
        return resp.json()


if __name__ == "__main__":
    chief = ChiefClient()
    decision = chief.propose(
        source="example-client",
        topic="dev.ci",
        summary="CI failed on main: test_auth_flow broken by PR #482",
        suggested_action="revert #482 or fix the fixture",
        evidence=["https://github.com/acme/repo/actions/runs/9"],
        claimed_urgency="high",
    )
    print(f"route={decision['route']}  score={decision.get('score')}")
    print(f"reason: {decision['reason']}")

    # Obey the route. Chief handles interrupt/digest/dispatch itself;
    # your job as a source is simply to NOT message the user directly.
    if decision["route"] == "drop":
        print("Chief judged this not worth anyone's attention. Trust it.")
