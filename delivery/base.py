"""Implements SPEC §4.3/§4.5: delivery-level abstraction and scene-capped selection.

Levels, weakest to strongest: terminal print < desktop notification <
Telegram silent < vibrate < Telegram ring.
"""

import re
from dataclasses import dataclass
from typing import Protocol

from context.infer import SCENE_POLICY

LEVELS = ["terminal", "desktop", "silent", "vibrate", "ring"]

# Untrusted event text reaches a terminal/notification. Strip C0/C1 control
# characters (ESC, NUL, BEL, …) so a hostile summary can't smuggle ANSI escape
# sequences into the terminal — keep only newline and tab. Rich-markup injection
# is handled separately at the terminal channel (Text() disables markup).
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")


def strip_control(text: str) -> str:
    return _CONTROL_RE.sub("", text)


@dataclass
class DeliveryMessage:
    summary: str
    event_id: str
    topic: str
    plan: str | None = None  # dispatch result, when arriving with a plan
    buttons: bool = True  # [Do it] [Later] [Mute this kind]


def render_message(msg: DeliveryMessage) -> str:
    """SPEC §4.5 template: `{summary}\\n{plan}\\n[Do it] [Later] [Mute this kind]`."""
    lines = [strip_control(msg.summary)]
    if msg.plan:
        lines.append(strip_control(msg.plan))
    if msg.buttons:
        lines.append("[Do it] [Later] [Mute this kind]")
    return "\n".join(lines)


def cap_level(requested: str, scene: str) -> str:
    """Clamp the requested level to the scene policy's max delivery level."""
    max_level = SCENE_POLICY[scene].max_level
    if LEVELS.index(requested) > LEVELS.index(max_level):
        return max_level
    return requested


class Channel(Protocol):
    name: str
    max_level: str  # strongest level this channel can express

    async def send(self, msg: DeliveryMessage, level: str) -> None: ...


def pick_channel(level: str, channels: list[Channel]):
    """Choose the weakest channel that can express `level`; if none can, the
    strongest available; if none at all, a fresh terminal channel."""
    from delivery.terminal import TerminalChannel

    if not channels:
        return TerminalChannel()
    capable = [c for c in channels if LEVELS.index(c.max_level) >= LEVELS.index(level)]
    if capable:
        return min(capable, key=lambda c: LEVELS.index(c.max_level))
    return max(channels, key=lambda c: LEVELS.index(c.max_level))


async def deliver(
    msg: DeliveryMessage, requested: str, scene: str, channels: list[Channel]
) -> str:
    """Cap by scene, pick a channel, send. Returns the level actually used."""
    level = cap_level(requested, scene)
    channel = pick_channel(level, channels)
    await channel.send(msg, level)
    return level
