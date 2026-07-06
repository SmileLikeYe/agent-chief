"""Composio connector (SPEC v3.2 Step 34): 500+ apps through one adapter.

Composio (composio.dev) pushes trigger events as a v3 envelope —
`{id, type, metadata:{trigger_slug,...}, data, timestamp}` — signed
svix-style: `webhook-signature` = base64 HMAC-SHA256 of
`{webhook-id}.{webhook-timestamp}.{raw body}` with the subscription secret.

This module only translates and verifies; judgment stays in the Brain.
"""

import base64
import hashlib
import hmac
import json
import time

REPLAY_TOLERANCE_SECONDS = 300  # svix-style freshness window

# trigger_slug prefix → Chief topic family (the unit of learning)
TOPIC_FAMILIES = {
    "GITHUB_": "dev.github.",
    "GITLAB_": "dev.gitlab.",
    "LINEAR_": "dev.linear.",
    "JIRA_": "dev.jira.",
    "GMAIL_": "comms.email.",
    "OUTLOOK_": "comms.email.",
    "SLACK_": "comms.slack.",
    "SLACKBOT_": "comms.slack.",
    "DISCORD_": "comms.discord.",
    "CALENDLY_": "calendar.",
    "GOOGLECALENDAR_": "calendar.",
    "STRIPE_": "finance.stripe.",
}

# fields that usually carry the human-readable one-liner, in preference order
SUMMARY_FIELDS = ("summary", "title", "subject", "message", "text", "name", "description")
LINK_FIELDS = ("html_url", "url", "link", "permalink")


def verify_signature(secret: str, msg_id: str, timestamp: str, body: bytes,
                     signature: str) -> bool:
    """svix-style: HMAC-SHA256(f"{id}.{timestamp}.") + raw body, base64."""
    if not secret or not signature:
        return False
    mac = hmac.new(secret.encode(), f"{msg_id}.{timestamp}.".encode() + body,
                   hashlib.sha256).digest()
    expected = base64.b64encode(mac).decode()
    # the header may carry multiple space-separated "v1,<sig>" entries; a
    # non-ASCII/garbage entry must never crash compare_digest — skip it
    for candidate in signature.split():
        candidate = candidate.removeprefix("v1,")
        try:
            if hmac.compare_digest(candidate, expected):
                return True
        except TypeError:
            continue
    return False


def timestamp_fresh(timestamp: str, now: float | None = None,
                    tolerance: int = REPLAY_TOLERANCE_SECONDS) -> bool:
    """Reject deliveries whose signed timestamp is outside the tolerance window
    (anti-replay). Non-numeric/blank timestamps fail closed."""
    try:
        ts = float(timestamp)
    except (TypeError, ValueError):
        return False
    return abs((now if now is not None else time.time()) - ts) <= tolerance


def _topic(slug: str) -> str:
    for prefix, family in TOPIC_FAMILIES.items():
        if slug.startswith(prefix):
            return family + slug.removeprefix(prefix).lower()
    return "composio." + slug.lower()


def _summary(slug: str, data: dict) -> str:
    for field in SUMMARY_FIELDS:
        value = data.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()[:200]
    return f"{slug}: {json.dumps(data, ensure_ascii=False)[:150]}"


def payload_to_event(envelope: dict) -> dict:
    """Composio v3 envelope → candidate-event payload for Brain.process."""
    meta = envelope.get("metadata") or {}
    data = envelope.get("data")
    if not isinstance(data, dict):  # batch/opaque payloads: wrap, never crash
        data = {"value": data} if data is not None else {}
    slug = meta.get("trigger_slug", "UNKNOWN")
    app = slug.split("_", 1)[0].lower() or "unknown"
    payload = {
        "source": f"composio:{app}",
        "topic": _topic(slug),
        "summary": _summary(slug, data),
        "dedup_key": envelope.get("id"),
    }
    evidence = [data[f] for f in LINK_FIELDS if isinstance(data.get(f), str)]
    if evidence:
        payload["evidence"] = evidence[:3]
    detail = json.dumps(data, ensure_ascii=False)
    if len(detail) <= 2000:
        payload["detail"] = detail
    return payload
