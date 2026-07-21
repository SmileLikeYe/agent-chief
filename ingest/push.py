"""The generic inbound *push* pipe (SPEC §4.1, generalized).

Chief already accepts events over HTTP (`POST /v1/events`), MCP (`propose`),
and the built-in pollers. This module makes "push attention from anywhere" a
first-class, one-line surface on top of that same `brain.process` entry:

- `push_payload(...)` is the minimal, forgiving envelope — `source` + `summary`
  are enough; topic is inferred, ids/dedup are filled by `normalize`. Both the
  `chief push` CLI and the Telegram inbound relay produce this shape, so there
  is exactly one contract to learn.
- `push_to_daemon(...)` is the client half of `chief push`: it reaches the
  running daemon's webhook with the local bearer token and returns the Decision.
- `describe_decision(...)` renders a Decision as a single human line, reused by
  the CLI output and the Telegram reply so both speak the same language.

Nothing here trusts the caller: `summary` is clamped to the schema's 200-char
limit and control characters never appear in a reply (that is handled at the
delivery edge). The pipe is content-blind — it hands the payload to the same
three-stage funnel every other source goes through.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import httpx

    from core.schema import Decision

DEFAULT_SOURCE = "push"
SUMMARY_MAX = 200  # mirrors Event.summary max_length; clamp before it 422s
URGENCIES = ("low", "medium", "high")  # mirrors Event.claimed_urgency


def push_payload(
    summary: str,
    *,
    source: str = DEFAULT_SOURCE,
    topic: str | None = None,
    claimed_urgency: str | None = None,
    detail: str | None = None,
    suggested_action: str | None = None,
) -> dict:
    """Build a candidate-event dict from the minimal push contract.

    Only `source` and `summary` are load-bearing; everything else is optional and
    dropped when absent so `normalize` can supply defaults (topic inference, id,
    dedup_key). The contract validates here — at the edge, before the network —
    so every caller (CLI, Telegram relay) fails fast with a human error instead
    of an opaque server 422: an empty summary and an unknown urgency both raise
    `ValueError`. `summary` is collapsed to one line ("one line a human could act
    on") and clamped to the schema limit so a long push degrades to a truncated
    event, never a validation error.
    """
    line = " ".join(summary.split())[:SUMMARY_MAX]
    if not line:
        raise ValueError("summary is empty — push needs one line a human could act on")
    if claimed_urgency is not None and claimed_urgency not in URGENCIES:
        raise ValueError(f"claimed_urgency must be one of {'/'.join(URGENCIES)}")
    payload: dict = {"source": source, "summary": line}
    if topic:
        payload["topic"] = topic
    if claimed_urgency:
        payload["claimed_urgency"] = claimed_urgency
    if detail:
        payload["detail"] = detail
    if suggested_action:
        payload["suggested_action"] = suggested_action
    return payload


def describe_decision(decision: Decision) -> str:
    """One human line: `interrupt · deep_work · score 4.2 — production incident`."""
    score = f"score {decision.score:.1f}" if decision.score is not None else "no score"
    return f"{decision.route} · {decision.scene} · {score} — {decision.reason}"


async def push_to_daemon(
    payload: dict,
    *,
    token: str,
    host: str = "127.0.0.1",
    port: int = 8787,
    transport: httpx.BaseTransport | None = None,
    timeout: float = 10.0,
) -> Decision:
    """POST a candidate event to the running daemon's webhook, return its Decision.

    This is the client half of `chief push`: any local script or skill can drive
    it. `transport` is injectable so tests can run it against the ASGI app in
    process. Raises `httpx.HTTPStatusError` on a non-2xx (bad token → 401).
    """
    import httpx

    from core.schema import Decision

    base_url = "http://push" if transport is not None else f"http://{host}:{port}"
    async with httpx.AsyncClient(transport=transport, base_url=base_url, timeout=timeout) as client:
        resp = await client.post(
            "/v1/events",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        resp.raise_for_status()
        return Decision.model_validate(resp.json())
