"""Implements SPEC §4.5: desktop notification channel via plyer, with terminal fallback."""

import logging
from collections.abc import Callable

from delivery.base import DeliveryMessage, render_message

logger = logging.getLogger(__name__)


def _plyer_notify(**kwargs) -> None:
    from plyer import notification

    notification.notify(**kwargs)


class DesktopChannel:
    name = "desktop"
    max_level = "desktop"

    def __init__(self, notify_fn: Callable[..., None] = _plyer_notify):
        self.notify_fn = notify_fn

    async def send(self, msg: DeliveryMessage, level: str) -> None:
        try:
            self.notify_fn(title="chief", message=render_message(msg), app_name="chief")
        except Exception as exc:  # no desktop session → degrade, never lose the message
            logger.warning("desktop notification failed (%s); falling back to terminal", exc)
            from delivery.terminal import TerminalChannel

            await TerminalChannel().send(msg, "terminal")
