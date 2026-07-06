"""Connector registry (SPEC v3.2 Step 34): out-of-the-box sources.

Every connector turns an external feed into candidate events through the one
ingest protocol — connectors fetch and translate, they never judge. Adding a
channel = one adapter module here plus a `connector_status` row; documented
slots are deliberately listed even before their adapter exists.
"""

from core.config import load_config


def connector_status() -> list[dict]:
    """What the console's Sources view and `chief sources` render."""
    cfg = load_config()
    ingest = cfg.get("ingest", {})
    connectors = cfg.get("connectors", {})
    composio = connectors.get("composio", {})
    return [
        {"name": "webhook", "connected": True,
         "detail": "POST /v1/events — any agent, any script (docs/protocol.md)"},
        {"name": "mcp", "connected": True,
         "detail": "propose/feedback/digest/policy/stats tools (python -m ingest.mcp_server)"},
        {"name": "composio", "connected": bool(composio.get("webhook_secret")),
         "detail": "GitHub / Gmail / Slack / 500+ apps via composio.dev triggers — "
                   "chief connect composio"},
        {"name": "github", "connected": bool(ingest.get("github")),
         "detail": "gh notifications poller (5 min) — chief connect github"},
        {"name": "rss", "connected": bool(ingest.get("rss_urls")),
         "detail": f"{len(ingest.get('rss_urls', []))} feeds, 30 min poller — "
                   "chief connect rss <url>"},
        {"name": "telegram", "connected": bool(cfg.get("delivery", {}).get("telegram_token")),
         "detail": "delivery + feedback buttons (not an ingest source)"},
        # documented slots — adapters welcome, same shape as composio
        {"name": "zapier / n8n", "connected": False,
         "detail": "slot: point any automation at POST /v1/events with a bearer token"},
        {"name": "mcp-push agents", "connected": False,
         "detail": "slot: Codex/Claude/other agents propose via MCP or chief lite"},
    ]
