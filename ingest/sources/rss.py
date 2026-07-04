"""Implements SPEC §4.1: rss source — any RSS/Atom url, poll every 30 min,
pure fetch→Event conversion (stdlib XML, no feed library)."""

import xml.etree.ElementTree as ET

import httpx

from ingest.sources.base import Poller

POLL_MINUTES = 30
_ATOM = "{http://www.w3.org/2005/Atom}"


def rss_to_payloads(xml_text: str) -> list[dict]:
    root = ET.fromstring(xml_text)
    payloads = []
    feed_title = (
        root.findtext("channel/title") or root.findtext(f"{_ATOM}title") or "feed"
    ).strip()

    items = root.findall("channel/item") or root.findall(f"{_ATOM}entry")
    for item in items:
        title = (item.findtext("title") or item.findtext(f"{_ATOM}title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if not link:
            link_el = item.find(f"{_ATOM}link")
            link = link_el.get("href", "") if link_el is not None else ""
        guid = (item.findtext("guid") or item.findtext(f"{_ATOM}id") or link or title).strip()
        payloads.append(
            {
                "source": "rss",
                "topic": "news.rss",
                "summary": f"{feed_title}: {title}"[:200],
                "evidence": [link] if link else [],
                "dedup_key": guid,
            }
        )
    return payloads


async def fetch_feed(url: str, transport=None) -> list[dict]:
    async with httpx.AsyncClient(transport=transport, timeout=20.0) as client:
        resp = await client.get(url, follow_redirects=True)
        resp.raise_for_status()
        return rss_to_payloads(resp.text)


def make_poller(url: str, submit, transport=None) -> Poller:
    async def fetch():
        return await fetch_feed(url, transport)

    return Poller(fetch=fetch, submit=submit, interval_minutes=POLL_MINUTES, name="rss")
