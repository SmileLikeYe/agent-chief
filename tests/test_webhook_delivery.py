"""Step 45 acceptance: the outbound delivery-webhook protocol.

One signed JSON POST turns any HTTP receiver into a delivery channel — the
inbound "protocol, not pipes" lesson applied to the exit. The signature is the
same svix scheme the Composio *inbound* connector verifies, so one verify
function covers both directions (a test proves the symmetry). Delivery retries,
then raises so the loss is logged, never silent.
"""

import json

import httpx
from typer.testing import CliRunner

from delivery.base import DeliveryMessage
from delivery.webhook import WebhookChannel, sign
from ingest.connectors.composio import verify_signature

runner = CliRunner()


def msg(**kw):
    defaults = dict(
        summary="Flight CA1857 delayed 2.5h",
        plan="Recommend MU5137 19:05.",
        event_id="evt_x",
        topic="travel.flight_change",
    )
    defaults.update(kw)
    return DeliveryMessage(**defaults)


def capture_transport(calls: list) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200)

    return httpx.MockTransport(handler)


# --- the receiver contract ---


async def test_send_posts_the_documented_json_shape():
    calls = []
    ch = WebhookChannel(url="https://receiver.local/hook", transport=capture_transport(calls))
    await ch.send(msg(), level="vibrate")

    body = json.loads(calls[0].content)
    assert body["event_id"] == "evt_x"
    assert body["topic"] == "travel.flight_change"
    assert body["summary"] == "Flight CA1857 delayed 2.5h"
    assert body["plan"] == "Recommend MU5137 19:05."
    assert body["level"] == "vibrate"  # receiver picks the noise from this
    assert "sent_at" in body


async def test_signature_verifies_with_the_inbound_verifier():
    """Outbound sign() and the Composio inbound verify_signature are the same
    svix scheme — one verify function covers both directions of the protocol."""
    calls = []
    ch = WebhookChannel(
        url="https://receiver.local/hook", secret="s3cret", transport=capture_transport(calls)
    )
    await ch.send(msg(), level="ring")

    req = calls[0]
    assert verify_signature(
        "s3cret",
        "evt_x",
        req.headers["chief-timestamp"],
        req.content,
        req.headers["chief-signature"],
    )
    # and a wrong secret must not verify
    assert not verify_signature(
        "wrong", "evt_x", req.headers["chief-timestamp"], req.content,
        req.headers["chief-signature"],
    )


async def test_no_secret_means_no_signature_headers():
    calls = []
    ch = WebhookChannel(url="https://receiver.local/hook", transport=capture_transport(calls))
    await ch.send(msg(), level="ring")
    assert "chief-signature" not in calls[0].headers
    assert "chief-timestamp" not in calls[0].headers


async def test_control_characters_never_reach_the_receiver():
    calls = []
    ch = WebhookChannel(url="https://receiver.local/hook", transport=capture_transport(calls))
    await ch.send(msg(summary="alert\x1b[2Jwiped", plan="do\x07this"), level="ring")
    body = json.loads(calls[0].content)
    assert body["summary"] == "alert[2Jwiped"
    assert body["plan"] == "dothis"


# --- failure behavior: retried, then loud ---


async def test_a_flaky_receiver_is_retried_to_success(monkeypatch):
    import delivery.webhook as wh

    monkeypatch.setattr(wh, "BACKOFF_SECONDS", 0)  # keep the test instant
    attempts = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        return httpx.Response(503 if len(attempts) < 3 else 200)

    ch = WebhookChannel(url="https://receiver.local/hook",
                        transport=httpx.MockTransport(handler))
    await ch.send(msg(), level="ring")  # no raise
    assert len(attempts) == 3


async def test_a_dead_receiver_raises_after_retries(monkeypatch):
    import pytest

    import delivery.webhook as wh

    monkeypatch.setattr(wh, "BACKOFF_SECONDS", 0)
    ch = WebhookChannel(
        url="https://receiver.local/hook",
        transport=httpx.MockTransport(lambda request: httpx.Response(503)),
    )
    # raises so brain._act_safely logs the loss — never a silent drop
    with pytest.raises(httpx.HTTPStatusError):
        await ch.send(msg(), level="ring")


# --- wiring: config → channel, connect → config ---


def test_make_channels_builds_the_webhook_channel_from_config():
    from cli.runtime import make_channels

    channels = make_channels({
        "webhook": {"url": "https://receiver.local/hook", "secret": "s", "max_level": "desktop"},
    })
    hooks = [c for c in channels if getattr(c, "name", "") == "webhook"]
    assert len(hooks) == 1
    assert hooks[0].max_level == "desktop" and hooks[0].secret == "s"

    assert all(
        getattr(c, "name", "") != "webhook" for c in make_channels({})
    )  # no url → no channel


def test_connect_webhook_writes_config_and_verifies_the_signer(tmp_path, monkeypatch):
    import tomllib

    monkeypatch.setenv("CHIEF_HOME", str(tmp_path))
    from cli.main import app

    result = runner.invoke(app, [
        "connect", "webhook", "--url", "https://receiver.local/hook", "--secret", "s3",
    ])
    assert result.exit_code == 0, result.output
    assert "signed sample verified" in result.output.lower()
    cfg = tomllib.loads((tmp_path / "config.toml").read_text(encoding="utf-8"))
    assert cfg["delivery"]["webhook"] == {
        "url": "https://receiver.local/hook", "max_level": "ring", "secret": "s3",
    }


def test_connect_webhook_warns_when_unsigned(tmp_path, monkeypatch):
    monkeypatch.setenv("CHIEF_HOME", str(tmp_path))
    from cli.main import app

    result = runner.invoke(app, ["connect", "webhook", "--url", "http://127.0.0.1:9099/x"])
    assert result.exit_code == 0, result.output
    assert "unsigned" in result.output.lower()


def test_connect_webhook_rejects_a_bad_url_and_level(tmp_path, monkeypatch):
    monkeypatch.setenv("CHIEF_HOME", str(tmp_path))
    from cli.main import app

    bad_url = runner.invoke(app, ["connect", "webhook", "--url", "ftp://nope"])
    assert bad_url.exit_code != 0

    bad_level = runner.invoke(app, [
        "connect", "webhook", "--url", "https://r.local/h", "--max-level", "shout",
    ])
    assert bad_level.exit_code != 0


def test_sign_is_deterministic_and_body_bound():
    a = sign("s", "evt_1", "100", b'{"x":1}')
    assert a == sign("s", "evt_1", "100", b'{"x":1}')
    assert a != sign("s", "evt_1", "100", b'{"x":2}')  # body-bound
    assert a != sign("s", "evt_2", "100", b'{"x":1}')  # id-bound
