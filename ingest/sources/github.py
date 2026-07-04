"""Implements SPEC §4.1: github_notifications source — `gh api notifications`,
poll every 5 min, pure fetch→Event conversion."""

import json
from typing import Any

from dispatch.executor import _default_exec
from ingest.sources.base import Poller

POLL_MINUTES = 5


def github_to_payloads(notifications: list[dict[str, Any]]) -> list[dict]:
    payloads = []
    for n in notifications:
        repo = n.get("repository", {}).get("full_name", "unknown/repo")
        subject = n.get("subject", {})
        kind = (subject.get("type") or "notification").lower()
        payloads.append(
            {
                "source": "github-notifications",
                "topic": f"github.{kind}",
                "summary": f"{repo}: {subject.get('title', '(no title)')}"[:200],
                "detail": f"reason: {n.get('reason', 'unknown')}",
                "evidence": [subject["url"]] if subject.get("url") else [],
                "dedup_key": f"gh-{n.get('id')}-{n.get('updated_at')}",
            }
        )
    return payloads


async def fetch_notifications(exec_fn=_default_exec) -> list[dict]:
    code, out, err = await exec_fn(["gh", "api", "notifications"], None)
    if code != 0:
        raise RuntimeError(f"gh api notifications failed: {err.strip()[:120]}")
    return github_to_payloads(json.loads(out))


def make_poller(submit, exec_fn=_default_exec) -> Poller:
    async def fetch():
        return await fetch_notifications(exec_fn)

    return Poller(fetch=fetch, submit=submit, interval_minutes=POLL_MINUTES, name="github")
