"""Implements SPEC §4.5: Telegram bot channel — silent vs ring modes, inline
feedback buttons ([Do it][Later][Mute this kind]) wired to the feedback table."""

import dataclasses
import logging
from datetime import UTC, datetime
from pathlib import Path

import httpx

from core.policy import add_muted_topic
from core.state import State
from delivery.base import DeliveryMessage, render_message

logger = logging.getLogger(__name__)

# button label → SPEC §4.6 feedback signal
BUTTONS = [
    ("Do it", "acted"),
    ("Later", "read"),
    ("Mute this kind", "muted"),
    # natural feedback (SPEC v3.2 Step 32)
    ("👍 Worth it", "should_interrupt"),
    ("👎 Not worth it", "should_not_interrupt"),
]


class TelegramChannel:
    name = "telegram"
    max_level = "ring"
    api = "https://api.telegram.org"

    def __init__(self, token: str, chat_id: str, transport=None, timeout: float = 30.0):
        self.token = token
        self.chat_id = chat_id
        self._transport = transport
        self.timeout = timeout

    async def send(self, msg: DeliveryMessage, level: str) -> None:
        keyboard = [
            {"text": label, "callback_data": f"fb|{signal}|{msg.event_id}|{msg.topic}"}
            for label, signal in BUTTONS
        ]
        payload = {
            "chat_id": self.chat_id,
            "text": render_message(dataclasses.replace(msg, buttons=False)),
            "disable_notification": level in ("silent", "vibrate"),
            "reply_markup": {"inline_keyboard": [keyboard]},
        }
        async with httpx.AsyncClient(transport=self._transport, timeout=self.timeout) as client:
            resp = await client.post(f"{self.api}/bot{self.token}/sendMessage", json=payload)
            resp.raise_for_status()

    async def _send_text(self, text: str) -> None:
        """Plain reply to the configured chat (used to echo a push decision)."""
        from delivery.base import strip_control

        async with httpx.AsyncClient(transport=self._transport, timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.api}/bot{self.token}/sendMessage",
                json={"chat_id": self.chat_id, "text": strip_control(text)},
            )
            resp.raise_for_status()

    async def ingest_message(self, message: dict, *, process):
        """Inbound relay: a message *to* the bot becomes a push event (SPEC §4.1).

        Reuses the already-trusted Telegram transport as the off-box inbound
        pipe, so a source that can't reach 127.0.0.1 can still push. Gated to the
        configured chat — a bot is reachable by anyone who finds it, so a message
        from any other chat is a stranger and is dropped, never ingested.
        """
        from ingest.push import describe_decision, push_payload

        if str(message.get("chat", {}).get("id")) != self.chat_id:
            logger.warning("ignoring telegram message from an unconfigured chat")
            return None
        text = (message.get("text") or "").strip()
        if not text:
            return None
        decision = await process(push_payload(text, source="telegram"))
        await self._send_text(f"🎩 {describe_decision(decision)}")
        return decision

    async def poll_callbacks(self, state: State, policy_path: str | Path, *, process=None) -> None:
        """Long-poll getUpdates: feed button presses into feedback capture and,
        when `process` is given, plain messages into the inbound push pipe."""
        offset = 0
        updates = ["callback_query"] + (["message"] if process else [])
        async with httpx.AsyncClient(transport=self._transport, timeout=None) as client:
            while True:
                resp = await client.post(
                    f"{self.api}/bot{self.token}/getUpdates",
                    json={"offset": offset, "timeout": 50, "allowed_updates": updates},
                )
                resp.raise_for_status()
                for update in resp.json().get("result", []):
                    offset = update["update_id"] + 1
                    cq = update.get("callback_query")
                    if cq:
                        await handle_callback(cq.get("data", ""), state, policy_path)
                        await client.post(
                            f"{self.api}/bot{self.token}/answerCallbackQuery",
                            json={"callback_query_id": cq["id"], "text": "noted"},
                        )
                    elif process and (msg := update.get("message")):
                        await self.ingest_message(msg, process=process)


async def handle_callback(data: str, state: State, policy_path: str | Path) -> None:
    """`fb|{signal}|{event_id}|{topic}` → feedback row (+ POLICY.md mute)."""
    parts = data.split("|")
    if len(parts) != 4 or parts[0] != "fb":
        logger.warning("ignoring malformed callback data: %r", data)
        return
    _, signal, event_id, topic = parts
    from core.learner import apply_feedback

    try:
        await apply_feedback(state, event_id, signal, datetime.now(UTC))
    except ValueError:
        logger.warning("ignoring unknown feedback signal: %r", signal)
        return
    if signal == "muted":
        add_muted_topic(policy_path, topic)  # Principle 3: effective immediately
