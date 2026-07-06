"""Step 34 acceptance (SPEC v3.2): connector framework + Composio adapter.

- HMAC signature verification rejects tampered payloads;
- GitHub/Gmail/Slack trigger fixtures become well-formed Events routed by the
  real pipeline; unknown slugs still ingest with a generic topic.
"""

import base64
import hashlib
import hmac
import json

import httpx
import pytest

from core.state import State
from ingest.connectors.composio import payload_to_event, verify_signature
from tests.helpers import StaticJudge, make_brain

SECRET = "whsec_test"


def envelope(slug, data, msg_id="msg_1"):
    return {
        "id": msg_id,
        "type": "composio.trigger.message",
        "metadata": {"trigger_slug": slug, "trigger_id": "ti_1",
                     "connected_account_id": "ca_1", "user_id": "u_1"},
        "data": data,
        "timestamp": "2026-07-06T10:00:00Z",
    }


def sign(body: bytes, msg_id="wh_1", ts=None):
    import time as _t
    ts = ts or str(int(_t.time()))
    mac = hmac.new(SECRET.encode(), f"{msg_id}.{ts}.".encode() + body,
                   hashlib.sha256).digest()
    return {"webhook-id": msg_id, "webhook-timestamp": ts,
            "webhook-signature": "v1," + base64.b64encode(mac).decode()}


# --- signature -------------------------------------------------------------------


def test_signature_roundtrip_and_tamper_rejection():
    body = json.dumps(envelope("GITHUB_COMMIT_EVENT", {"message": "m"})).encode()
    h = sign(body)
    assert verify_signature(SECRET, h["webhook-id"], h["webhook-timestamp"],
                            body, h["webhook-signature"])
    assert not verify_signature(SECRET, h["webhook-id"], h["webhook-timestamp"],
                                body + b" ", h["webhook-signature"])
    assert not verify_signature("wrong", h["webhook-id"], h["webhook-timestamp"],
                                body, h["webhook-signature"])


# --- envelope → event mapping -------------------------------------------------------


def test_trigger_slug_topic_families():
    cases = {
        "GITHUB_COMMIT_EVENT": "dev.github.commit_event",
        "GITHUB_PULL_REQUEST_EVENT": "dev.github.pull_request_event",
        "GMAIL_NEW_GMAIL_MESSAGE": "comms.email.new_gmail_message",
        "SLACK_RECEIVE_MESSAGE": "comms.slack.receive_message",
        "NOTION_PAGE_ADDED": "composio.notion_page_added",  # unknown family
    }
    for slug, topic in cases.items():
        payload = payload_to_event(envelope(slug, {"message": "hello"}))
        assert payload["topic"] == topic, slug
        assert payload["source"].startswith("composio")


def test_summary_extraction_prefers_human_fields():
    p = payload_to_event(envelope("GMAIL_NEW_GMAIL_MESSAGE",
                                  {"subject": "Invoice overdue", "from": "x"}))
    assert p["summary"] == "Invoice overdue"
    p = payload_to_event(envelope("GITHUB_COMMIT_EVENT",
                                  {"message": "fix: null pointer", "author": "jane"}))
    assert p["summary"] == "fix: null pointer"
    p = payload_to_event(envelope("X_OPAQUE", {"weird": {"nested": 1}}))
    assert "X_OPAQUE" in p["summary"]  # graceful fallback, never crashes
    assert len(p["summary"]) <= 200


# --- inbound webhook end-to-end -------------------------------------------------------


@pytest.fixture
async def client(tmp_path):
    from ingest.http import create_app

    async with State.open(tmp_path / "s.db") as state:
        brain = make_brain(state, tmp_path, judge=StaticJudge())
        app = create_app(brain, token="sekrit",
                         connectors={"composio": {"webhook_secret": SECRET}})
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            yield c


async def test_signed_trigger_routes_through_real_pipeline(client):
    body = json.dumps(envelope("GITHUB_PULL_REQUEST_EVENT",
                               {"title": "Fix login race", "html_url": "https://x/pr/1"}))
    resp = await client.post("/v1/connectors/composio", content=body,
                             headers=sign(body.encode()))
    assert resp.status_code == 200
    d = resp.json()
    assert d["route"] in ("interrupt", "digest", "dispatch", "curate", "drop")
    assert d["reason"]


async def test_tampered_delivery_is_rejected(client):
    body = json.dumps(envelope("SLACK_RECEIVE_MESSAGE", {"text": "hey"}))
    headers = sign(body.encode())
    resp = await client.post("/v1/connectors/composio",
                             content=body.replace("hey", "hoax"), headers=headers)
    assert resp.status_code == 401


async def test_unconfigured_connector_returns_503(tmp_path):
    from ingest.http import create_app

    async with State.open(tmp_path / "s.db") as state:
        brain = make_brain(state, tmp_path, judge=StaticJudge())
        app = create_app(brain, token="sekrit")  # no connectors config
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            resp = await c.post("/v1/connectors/composio", content="{}",
                                headers=sign(b"{}"))
            assert resp.status_code == 503


async def test_stale_delivery_is_rejected(client):
    body = json.dumps(envelope("GITHUB_COMMIT_EVENT", {"message": "old"}))
    stale = sign(body.encode(), ts="1000000000")  # year 2001, well outside tolerance
    resp = await client.post("/v1/connectors/composio", content=body, headers=stale)
    assert resp.status_code == 401  # replay protection


async def test_non_dict_data_does_not_crash():
    for data in ([1, 2, 3], "plain string", None):
        p = payload_to_event(envelope("X_BATCH", data))
        assert isinstance(p["summary"], str) and p["topic"].startswith("composio")


def test_non_ascii_signature_header_never_crashes():
    assert verify_signature("s", "id", "1", b"{}", "v1,\xe9garbage") is False
