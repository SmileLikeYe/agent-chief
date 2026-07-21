"""The generic outbound pipe (SPEC §4.5, generalized): delivery as a protocol.

Chief doesn't grow a bespoke adapter per notification app — that's the inbound
lesson ("protocol, not pipes") applied to the exit. A WebhookChannel POSTs one
signed JSON shape to a URL you configure; anything that can receive an HTTP
POST — a phone-app bridge, an ntfy relay you host, a desktop applet — becomes a
delivery channel by implementing one receiver. The §13 stance is unchanged: no
team-chat adapters ship here; this is a neutral egress to *your* receiver, the
same personal-delivery posture as the Telegram channel.

The receiver contract (documented in docs/protocol.md §4):

    POST <your url>
    chief-timestamp: <unix seconds>
    chief-signature: v1,<base64 HMAC-SHA256 over "{event_id}.{timestamp}." + body>
    {"event_id", "topic", "summary", "plan", "level", "sent_at"}

The signature scheme is byte-for-byte the svix style already used by the
Composio *inbound* connector, so one verify function covers both directions.
Signing happens only when a secret is configured — but configure one: an
unsigned receiver can't tell Chief from anyone who found its URL.

Delivery is retried (the actor task is already off the hot path), then raised —
brain._act_safely logs it. An interrupt whose receiver is down is lost, not
queued; that honest limitation is documented, not hidden.
"""

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import time

import httpx

from delivery.base import DeliveryMessage, strip_control

logger = logging.getLogger(__name__)

ATTEMPTS = 3
BACKOFF_SECONDS = 0.5  # 0.5s, 1s between the three attempts


def sign(secret: str, event_id: str, timestamp: str, body: bytes) -> str:
    """svix-style, mirroring ingest.connectors.composio.verify_signature."""
    mac = hmac.new(
        secret.encode(), f"{event_id}.{timestamp}.".encode() + body, hashlib.sha256
    ).digest()
    return f"v1,{base64.b64encode(mac).decode()}"


class WebhookChannel:
    """POST deliveries to one configured receiver; the receiver picks the noise."""

    name = "webhook"

    def __init__(
        self,
        url: str,
        secret: str | None = None,
        max_level: str = "ring",
        transport=None,
        timeout: float = 10.0,
    ):
        self.url = url
        self.secret = secret
        self.max_level = max_level
        self._transport = transport
        self.timeout = timeout

    async def send(self, msg: DeliveryMessage, level: str) -> None:
        payload = {
            "event_id": msg.event_id,
            "topic": msg.topic,
            "summary": strip_control(msg.summary),
            "plan": strip_control(msg.plan) if msg.plan else None,
            "level": level,
            "sent_at": time.time(),
        }
        body = json.dumps(payload).encode()
        headers = {"content-type": "application/json"}
        if self.secret:
            timestamp = str(int(payload["sent_at"]))
            headers["chief-timestamp"] = timestamp
            headers["chief-signature"] = sign(self.secret, msg.event_id, timestamp, body)

        async with httpx.AsyncClient(transport=self._transport, timeout=self.timeout) as client:
            for attempt in range(1, ATTEMPTS + 1):
                try:
                    resp = await client.post(self.url, content=body, headers=headers)
                    resp.raise_for_status()
                    return
                except httpx.HTTPError as exc:
                    if attempt == ATTEMPTS:
                        raise  # brain._act_safely logs it; the loss is not silent
                    logger.warning(
                        "webhook delivery attempt %d/%d failed (%s); retrying",
                        attempt, ATTEMPTS, exc,
                    )
                    await asyncio.sleep(BACKOFF_SECONDS * attempt)
