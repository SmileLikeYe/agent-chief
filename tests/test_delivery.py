"""Step 10 acceptance: level-capping unit tests (meeting caps at silent push);
terminal + desktop channels; graceful fallback."""

import pytest

from delivery.base import LEVELS, DeliveryMessage, cap_level, pick_channel, render_message
from delivery.desktop import DesktopChannel
from delivery.terminal import TerminalChannel


def msg(**kw):
    defaults = dict(
        summary="Flight CA1857 delayed 2.5h",
        plan="3 rebooking options found. Recommend MU5137 19:05.",
        event_id="evt_x",
        topic="travel.flight_change",
    )
    defaults.update(kw)
    return DeliveryMessage(**defaults)


# --- level ordering + scene caps (SPEC §4.3) ---


def test_levels_are_ordered():
    assert LEVELS == ["terminal", "desktop", "silent", "vibrate", "ring"]


@pytest.mark.parametrize(
    ("requested", "scene", "expected"),
    [
        ("ring", "meeting", "silent"),  # meeting caps at silent push
        ("ring", "deep_work", "silent"),
        ("ring", "social", "vibrate"),
        ("ring", "idle", "ring"),
        ("ring", "commuting", "ring"),
        ("terminal", "meeting", "terminal"),  # never raises a level
        ("desktop", "leisure", "desktop"),
    ],
)
def test_cap_level(requested, scene, expected):
    assert cap_level(requested, scene) == expected


# --- message template (SPEC §4.5) ---


def test_render_message_with_plan_and_buttons():
    text = render_message(msg())
    lines = text.splitlines()
    assert lines[0] == "Flight CA1857 delayed 2.5h"
    assert "3 rebooking options" in lines[1]
    assert lines[-1] == "[Do it] [Later] [Mute this kind]"


def test_render_message_without_plan():
    text = render_message(msg(plan=None))
    assert "\n\n" not in text
    assert text.splitlines()[-1] == "[Do it] [Later] [Mute this kind]"


# --- channels ---


async def test_terminal_channel_prints(capsys):
    ch = TerminalChannel()
    await ch.send(msg(), level="terminal")
    out = capsys.readouterr().out
    assert "Flight CA1857 delayed" in out


async def test_desktop_channel_calls_plyer(monkeypatch):
    calls = []
    ch = DesktopChannel(notify_fn=lambda **kw: calls.append(kw))
    await ch.send(msg(), level="desktop")
    assert calls and "Flight CA1857" in calls[0]["message"]


async def test_desktop_channel_falls_back_to_terminal(capsys):
    def broken(**kw):
        raise RuntimeError("no notification daemon")

    ch = DesktopChannel(notify_fn=broken)
    await ch.send(msg(), level="desktop")
    assert "Flight CA1857" in capsys.readouterr().out  # degraded, not lost


def test_pick_channel_by_level():
    terminal, desktop = TerminalChannel(), DesktopChannel(notify_fn=lambda **kw: None)
    channels = [terminal, desktop]
    assert pick_channel("terminal", channels) is terminal
    assert pick_channel("desktop", channels) is desktop
    # no telegram configured: higher levels degrade to the best available
    assert pick_channel("ring", channels) is desktop


def test_pick_channel_empty_falls_back_to_terminal():
    assert isinstance(pick_channel("ring", []), TerminalChannel)
