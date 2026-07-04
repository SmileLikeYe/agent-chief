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
BUTTONS = [("Do it", "acted"), ("Later", "read"), ("Mute this kind", "muted")]


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

    async def poll_callbacks(self, state: State, policy_path: str | Path) -> None:
        """Long-poll getUpdates and feed button presses into feedback capture."""
        offset = 0
        async with httpx.AsyncClient(transport=self._transport, timeout=None) as client:
            while True:
                resp = await client.post(
                    f"{self.api}/bot{self.token}/getUpdates",
                    json={"offset": offset, "timeout": 50, "allowed_updates": ["callback_query"]},
                )
                for update in resp.json().get("result", []):
                    offset = update["update_id"] + 1
                    cq = update.get("callback_query")
                    if cq:
                        await handle_callback(cq.get("data", ""), state, policy_path)
                        await client.post(
                            f"{self.api}/bot{self.token}/answerCallbackQuery",
                            json={"callback_query_id": cq["id"], "text": "noted"},
                        )


async def handle_callback(data: str, state: State, policy_path: str | Path) -> None:
    """`fb|{signal}|{event_id}|{topic}` → feedback row (+ POLICY.md mute)."""
    parts = data.split("|")
    if len(parts) != 4 or parts[0] != "fb":
        logger.warning("ignoring malformed callback data: %r", data)
        return
    _, signal, event_id, topic = parts
    await state.save_feedback(event_id, signal, datetime.now(UTC))
    if signal == "muted":
        add_muted_topic(policy_path, topic)  # Principle 3: effective immediately
