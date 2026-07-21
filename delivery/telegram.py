"""Implements SPEC §4.5 (outbound) + §4.1 (inbound relay): Telegram bot channel.

Outbound: silent vs ring modes, inline feedback buttons ([Do it][Later][Mute
this kind]) wired to the feedback table. Inbound: a message *to* the bot becomes
a push event — the off-box half of the push pipe (Step 44)."""

import asyncio
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

        A message longer than the one-line summary keeps its full text in
        `detail` — clamping is a rendering concern, never data loss. The reply is
        best-effort: once `process` has decided (and persisted), a failed echo
        must not undo or mask that, so send errors are logged and swallowed.
        """
        from ingest.push import describe_decision, push_payload

        if str(message.get("chat", {}).get("id")) != self.chat_id:
            logger.warning("ignoring telegram message from an unconfigured chat")
            return None
        text = (message.get("text") or "").strip()
        if not text:
            return None
        payload = push_payload(text, source="telegram")
        if payload["summary"] != text:  # collapsed or clamped → keep the original
            payload["detail"] = text
        decision = await process(payload)
        try:
            await self._send_text(f"🎩 {describe_decision(decision)}")
        except httpx.HTTPError as exc:
            logger.warning("telegram reply failed (%s); decision %s stands", exc, decision.route)
        return decision

    async def _handle_update(self, update: dict, client, state, policy_path, process) -> None:
        """Dispatch one getUpdates entry to the callback or inbound-push path."""
        cq = update.get("callback_query")
        if cq:
            await handle_callback(cq.get("data", ""), state, policy_path)
            await client.post(
                f"{self.api}/bot{self.token}/answerCallbackQuery",
                json={"callback_query_id": cq["id"], "text": "noted"},
            )
        elif process and (msg := update.get("message")):
            await self.ingest_message(msg, process=process)

    async def _poll_once(
        self, client, offset: int, updates: list[str], state, policy_path, process
    ) -> int:
        """One getUpdates round. Returns the next offset.

        The offset advances past every update in the batch *before* it is
        handled, and a failing update is logged and skipped — a poison update
        must cost exactly itself: never the rest of the batch, never the loop,
        and never a redelivery storm on the next round.
        """
        resp = await client.post(
            f"{self.api}/bot{self.token}/getUpdates",
            json={"offset": offset, "timeout": 50, "allowed_updates": updates},
        )
        resp.raise_for_status()
        for update in resp.json().get("result", []):
            if "update_id" in update:
                offset = update["update_id"] + 1
            try:
                await self._handle_update(update, client, state, policy_path, process)
            except Exception:
                logger.exception("telegram update %s failed; skipped", update.get("update_id"))
        return offset

    async def poll_callbacks(self, state: State, policy_path: str | Path, *, process=None) -> None:
        """Long-poll getUpdates: feed button presses into feedback capture and,
        when `process` is given, plain messages into the inbound push pipe.

        This task must outlive the network: it is the phone's only path in and
        out, so a Telegram 5xx / timeout / bad body is retried with capped
        exponential backoff instead of killing the task for the daemon's life.
        """
        offset = 0
        delay = 1.0
        updates = ["callback_query"] + (["message"] if process else [])
        async with httpx.AsyncClient(transport=self._transport, timeout=None) as client:
            while True:
                try:
                    offset = await self._poll_once(
                        client, offset, updates, state, policy_path, process
                    )
                    delay = 1.0
                except (httpx.HTTPError, ValueError) as exc:  # ValueError: non-JSON body
                    logger.warning("telegram getUpdates failed (%s); retry in %.0fs", exc, delay)
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, 60.0)


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
