"""Step 19 acceptance: fixture-fed converter tests produce well-formed Events;
poller respects intervals (mock clock)."""

import json
from datetime import UTC, datetime, timedelta

from ingest.normalize import normalize
from ingest.sources.base import Poller
from ingest.sources.github import github_to_payloads
from ingest.sources.rss import rss_to_payloads

NOW = datetime(2026, 7, 6, 10, 0, tzinfo=UTC)

GH_FIXTURE = json.dumps(
    [
        {
            "id": "123",
            "updated_at": "2026-07-06T09:55:00Z",
            "reason": "ci_activity",
            "repository": {"full_name": "SmileLikeYe/agent-chief"},
            "subject": {
                "title": "CI failed on main",
                "type": "CheckSuite",
                "url": "https://api.github.com/repos/SmileLikeYe/agent-chief/check-suites/9",
            },
        },
        {
            "id": "124",
            "updated_at": "2026-07-06T09:50:00Z",
            "reason": "review_requested",
            "repository": {"full_name": "acme/widgets"},
            "subject": {
                "title": "Add rate limiter",
                "type": "PullRequest",
                "url": "https://api.github.com/repos/acme/widgets/pulls/42",
            },
        },
    ]
)

RSS_FIXTURE = """<?xml version="1.0"?>
<rss version="2.0"><channel>
  <title>XX Engineering Blog</title>
  <item>
    <title>XX SDK 2.0 release announcement</title>
    <link>https://xx.dev/blog/sdk-2</link>
    <guid>xx-sdk-2</guid>
  </item>
  <item>
    <title>Scaling our ingest pipeline</title>
    <link>https://xx.dev/blog/ingest</link>
  </item>
</channel></rss>"""


async def test_github_converter_produces_well_formed_events():
    payloads = github_to_payloads(json.loads(GH_FIXTURE))
    assert len(payloads) == 2
    first = payloads[0]
    assert first["source"] == "github-notifications"
    assert first["topic"] == "github.checksuite"
    assert "SmileLikeYe/agent-chief" in first["summary"]
    assert first["dedup_key"] == "gh-123-2026-07-06T09:55:00Z"
    event = await normalize(first, now=NOW)  # normalizes into a valid Event
    assert event.evidence


async def test_rss_converter_produces_well_formed_events():
    payloads = rss_to_payloads(RSS_FIXTURE)
    assert len(payloads) == 2
    first = payloads[0]
    assert first["source"] == "rss"
    assert first["summary"] == "XX Engineering Blog: XX SDK 2.0 release announcement"
    assert first["evidence"] == ["https://xx.dev/blog/sdk-2"]
    assert first["dedup_key"] == "xx-sdk-2"
    second = payloads[1]
    assert second["dedup_key"] == "https://xx.dev/blog/ingest"  # falls back to link
    event = await normalize(first, now=NOW)
    assert event.topic == "news.rss"


def test_converters_contain_no_judgment():
    """Sources only fetch/convert (SPEC §4.1); no scores, no routes."""
    for payload in github_to_payloads(json.loads(GH_FIXTURE)) + rss_to_payloads(RSS_FIXTURE):
        assert "route" not in payload and "score" not in payload


# --- poller interval discipline (mock clock) ---


async def test_poller_respects_interval():
    fetches = []

    async def fetch():
        fetches.append(1)
        return []

    async def submit(payload):
        raise AssertionError("nothing to submit")

    poller = Poller(fetch=fetch, submit=submit, interval_minutes=5)
    await poller.tick(NOW)
    await poller.tick(NOW + timedelta(minutes=1))  # too soon
    await poller.tick(NOW + timedelta(minutes=4, seconds=59))  # still too soon
    assert len(fetches) == 1
    await poller.tick(NOW + timedelta(minutes=5))
    assert len(fetches) == 2


async def test_poller_submits_each_payload():
    submitted = []

    async def fetch():
        return [{"summary": "a"}, {"summary": "b"}]

    async def submit(payload):
        submitted.append(payload["summary"])

    poller = Poller(fetch=fetch, submit=submit, interval_minutes=5)
    await poller.tick(NOW)
    assert submitted == ["a", "b"]


async def test_poller_survives_fetch_errors():
    async def fetch():
        raise RuntimeError("network down")

    async def submit(payload):
        pass

    poller = Poller(fetch=fetch, submit=submit, interval_minutes=5)
    await poller.tick(NOW)  # must not raise
    await poller.tick(NOW + timedelta(minutes=5))
