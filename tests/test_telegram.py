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


# --- inbound relay (Step 44): a message to the bot becomes a push event ---


def make_decision(**kw):
    from core.schema import Decision

    base = dict(
        event_id="evt_z", route="digest", score=1.2, scene="idle",
        scene_confidence=0.4, cost=0.0, reason="scored low", stage=3,
    )
    base.update(kw)
    return Decision(**base)


async def test_inbound_message_becomes_a_push_event_and_gets_a_reply():
    seen = []

    async def process(payload):
        seen.append(payload)
        return make_decision()

    calls = []
    ch = TelegramChannel(token="TOK", chat_id="42", transport=capture_transport(calls))
    message = {"chat": {"id": 42}, "text": "flaky test on CI again"}
    decision = await ch.ingest_message(message, process=process)

    assert seen == [{"source": "telegram", "summary": "flaky test on CI again"}]
    assert decision is not None
    # a reply went back to the same chat, echoing the decision
    path, body = calls[0]
    assert path == "/botTOK/sendMessage" and body["chat_id"] == "42"
    assert "digest" in body["text"] and "scored low" in body["text"]


async def test_inbound_message_from_a_stranger_chat_is_dropped():
    called = []

    async def process(payload):
        called.append(payload)
        return make_decision()

    calls = []
    ch = TelegramChannel(token="TOK", chat_id="42", transport=capture_transport(calls))
    # a bot is reachable by anyone; a message from any other chat must not ingest
    decision = await ch.ingest_message({"chat": {"id": 999}, "text": "inject"}, process=process)
    assert decision is None
    assert called == [] and calls == []


async def test_inbound_empty_message_is_ignored():
    async def process(payload):
        raise AssertionError("should not be called for an empty message")

    ch = TelegramChannel(token="TOK", chat_id="42", transport=capture_transport([]))
    assert await ch.ingest_message({"chat": {"id": 42}, "text": "   "}, process=process) is None


async def test_inbound_long_message_keeps_full_text_in_detail():
    """Clamping is a rendering concern, never data loss: a 4096-char Telegram
    message arrives with a one-line summary and the original intact in detail."""
    seen = []

    async def process(payload):
        seen.append(payload)
        return make_decision()

    ch = TelegramChannel(token="TOK", chat_id="42", transport=capture_transport([]))
    long_text = "incident report: " + "x" * 400
    await ch.ingest_message({"chat": {"id": 42}, "text": long_text}, process=process)
    assert len(seen[0]["summary"]) == 200
    assert seen[0]["detail"] == long_text


async def test_inbound_multiline_message_summarizes_to_one_line():
    seen = []

    async def process(payload):
        seen.append(payload)
        return make_decision()

    ch = TelegramChannel(token="TOK", chat_id="42", transport=capture_transport([]))
    await ch.ingest_message({"chat": {"id": 42}, "text": "CI failed\non main"}, process=process)
    assert seen[0]["summary"] == "CI failed on main"
    assert seen[0]["detail"] == "CI failed\non main"


async def test_inbound_reply_failure_never_loses_the_decision():
    """Once process() has decided (and persisted), a failed echo is logged and
    swallowed — the reply is best-effort, the decision is not."""
    ch = TelegramChannel(
        token="TOK", chat_id="42",
        transport=httpx.MockTransport(lambda request: httpx.Response(502)),
    )

    async def process(payload):
        return make_decision()

    decision = await ch.ingest_message({"chat": {"id": 42}, "text": "hi"}, process=process)
    assert decision is not None and decision.route == "digest"


async def test_a_poison_update_costs_itself_not_the_batch(tmp_path):
    """One update whose handling explodes is skipped; the rest of the batch still
    lands and the offset passes everything — no redelivery storm, no dead loop."""
    batch = {
        "ok": True,
        "result": [
            {"update_id": 7, "message": {"chat": {"id": 42}, "text": "boom"}},
            {"update_id": 8, "message": {"chat": {"id": 42}, "text": "fine"}},
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/getUpdates"):
            return httpx.Response(200, json=batch)
        return httpx.Response(200, json={"ok": True, "result": {}})

    seen = []

    async def process(payload):
        if payload["summary"] == "boom":
            raise RuntimeError("judge exploded")
        seen.append(payload["summary"])
        return make_decision()

    ch = TelegramChannel(token="TOK", chat_id="42", transport=httpx.MockTransport(handler))
    async with State.open(tmp_path / "s.db") as state:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            offset = await ch._poll_once(
                client, 0, ["message"], state, tmp_path / "POLICY.md", process
            )
    assert offset == 9  # past BOTH updates — the poison one is never redelivered
    assert seen == ["fine"]


async def test_shutdown_acks_handled_updates_so_restart_does_not_replay(tmp_path):
    """Cancelling the poll task fires one last offset-only getUpdates, so
    Telegram never redelivers an already-handled batch after a daemon restart
    (duplicate feedback rows, re-ingested pushes, reply noise)."""
    import asyncio

    import pytest

    requests: list[dict] = []
    batch = {"ok": True, "result": [
        {"update_id": 7, "message": {"chat": {"id": 42}, "text": "hello"}},
    ]}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/getUpdates"):
            requests.append(json.loads(request.content))
            if len(requests) == 1:
                return httpx.Response(200, json=batch)
            raise httpx.ConnectError("network gone")  # push the loop into backoff
        return httpx.Response(200, json={"ok": True, "result": {}})

    async def process(payload):
        from tests.test_telegram import make_decision

        return make_decision()

    ch = TelegramChannel(token="TOK", chat_id="42", transport=httpx.MockTransport(handler))
    async with State.open(tmp_path / "s.db") as state:
        task = asyncio.ensure_future(
            ch.poll_callbacks(state, tmp_path / "POLICY.md", process=process)
        )
        for _ in range(200):  # wait until the loop is parked in backoff sleep
            if len(requests) >= 2:
                break
            await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    ack = requests[-1]
    assert ack["offset"] == 8 and ack["timeout"] == 0  # handled batch acknowledged


async def test_a_getupdates_failure_raises_for_the_backoff_loop(tmp_path):
    """_poll_once lets transport errors propagate — poll_callbacks catches them
    and retries with backoff instead of dying for the daemon's life."""
    import pytest

    ch = TelegramChannel(
        token="TOK", chat_id="42",
        transport=httpx.MockTransport(lambda request: httpx.Response(502)),
    )
    async with State.open(tmp_path / "s.db") as state:
        async with httpx.AsyncClient(transport=ch._transport) as client:
            with pytest.raises(httpx.HTTPStatusError):
                await ch._poll_once(client, 0, ["message"], state, tmp_path / "POLICY.md", None)


def test_add_muted_topic_creates_and_appends(tmp_path):
    p = tmp_path / "POLICY.md"
    add_muted_topic(p, "a.b")
    add_muted_topic(p, "c.d")
    add_muted_topic(p, "a.b")  # idempotent
    policy = load_policy(p)
    assert policy.is_muted("a.b") and policy.is_muted("c.d")
    assert p.read_text().count("- a.b") == 1
