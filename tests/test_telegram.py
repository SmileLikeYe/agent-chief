"""Step 11 acceptance: telegram test double — silent vs ring modes; button
callback → correct signal row in the feedback table; mute updates POLICY.md."""

import json

import httpx

from core.policy import add_muted_topic, load_policy
from core.state import State
from delivery.base import DeliveryMessage
from delivery.telegram import TelegramChannel, handle_callback


def capture_transport(calls: list) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.url.path, json.loads(request.content)))
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})

    return httpx.MockTransport(handler)


def msg(**kw):
    defaults = dict(
        summary="Flight CA1857 delayed 2.5h",
        plan="Recommend MU5137 19:05.",
        event_id="evt_x",
        topic="travel.flight_change",
    )
    defaults.update(kw)
    return DeliveryMessage(**defaults)


async def test_send_ring_mode():
    calls = []
    ch = TelegramChannel(token="TOK", chat_id="42", transport=capture_transport(calls))
    await ch.send(msg(), level="ring")
    path, body = calls[0]
    assert path == "/botTOK/sendMessage"
    assert body["chat_id"] == "42"
    assert body["disable_notification"] is False
    assert "Flight CA1857" in body["text"] and "Recommend MU5137" in body["text"]


async def test_send_silent_mode():
    calls = []
    ch = TelegramChannel(token="TOK", chat_id="42", transport=capture_transport(calls))
    await ch.send(msg(), level="silent")
    assert calls[0][1]["disable_notification"] is True


async def test_inline_buttons_carry_feedback_callbacks():
    calls = []
    ch = TelegramChannel(token="TOK", chat_id="42", transport=capture_transport(calls))
    await ch.send(msg(), level="ring")
    keyboard = calls[0][1]["reply_markup"]["inline_keyboard"][0]
    labels = [b["text"] for b in keyboard]
    # Step 32 (v3.2): natural-feedback buttons ride along
    assert labels == [
        "Do it", "Later", "Mute this kind", "👍 Worth it", "👎 Not worth it"
    ]
    datas = [b["callback_data"] for b in keyboard]
    assert datas[0] == "fb|acted|evt_x|travel.flight_change"
    assert datas[1] == "fb|read|evt_x|travel.flight_change"
    assert datas[2] == "fb|muted|evt_x|travel.flight_change"


async def test_button_callback_writes_feedback_row(tmp_path):
    async with State.open(tmp_path / "s.db") as state:
        await handle_callback("fb|acted|evt_x|travel.flight_change", state,
                              policy_path=tmp_path / "POLICY.md")
        rows = await state.feedback_rows()
        assert len(rows) == 1
        assert rows[0]["event_id"] == "evt_x" and rows[0]["signal"] == "acted"


async def test_mute_button_updates_policy_immediately(tmp_path):
    policy_path = tmp_path / "POLICY.md"
    async with State.open(tmp_path / "s.db") as state:
        await handle_callback("fb|muted|evt_x|marketing.webinar", state, policy_path=policy_path)
        rows = await state.feedback_rows()
        assert rows[0]["signal"] == "muted"
    assert load_policy(policy_path).is_muted("marketing.webinar")


async def test_malformed_callback_ignored(tmp_path):
    async with State.open(tmp_path / "s.db") as state:
        await handle_callback("garbage", state, policy_path=tmp_path / "POLICY.md")
        assert await state.feedback_rows() == []


def test_add_muted_topic_creates_and_appends(tmp_path):
    p = tmp_path / "POLICY.md"
    add_muted_topic(p, "a.b")
    add_muted_topic(p, "c.d")
    add_muted_topic(p, "a.b")  # idempotent
    policy = load_policy(p)
    assert policy.is_muted("a.b") and policy.is_muted("c.d")
    assert p.read_text().count("- a.b") == 1
