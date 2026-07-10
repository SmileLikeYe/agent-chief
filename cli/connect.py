"""SPEC v3.2 Step 35: one-click source connection.

`chief connect <source>` edits ~/.chief/config.toml surgically (everything
else preserved) and prints the exact next actions. Config writing stays
dependency-free: our schema is flat sections (plus one nested `connectors.*`
level) of strings/bools/ints/string-lists, so a tiny serializer suffices.
"""

import base64
import hashlib
import hmac
import json
import tomllib

from rich.console import Console

from core.config import (
    UnsupportedConfig,
    config_path,
    load_config,
    serialize_config,
    write_private_text,
)

console = Console(soft_wrap=True, highlight=False)  # keep URLs copy-pastable


def _update_config(mutate) -> dict:
    path = config_path()
    raw = path.read_text(encoding="utf-8") if path.exists() else ""
    cfg = tomllib.loads(raw) if raw else {}
    mutate(cfg)
    try:
        rendered = serialize_config(cfg)
    except UnsupportedConfig as exc:
        raise SystemExit(
            f"chief connect can't safely rewrite {path} ({exc}).\n"
            f"Edit the config by hand — add the section shown in the docs — and re-run."
        ) from exc
    if raw:
        write_private_text(path.with_suffix(".toml.bak"), raw)
    write_private_text(path, rendered)
    return cfg


def connect_composio(secret: str) -> None:
    _update_config(
        lambda cfg: cfg.setdefault("connectors", {}).setdefault("composio", {}).update(
            {"webhook_secret": secret}
        )
    )
    port = load_config().get("ingest", {}).get("webhook_port", 8787)

    # prove the secret + verifier agree before the user leaves the terminal
    from ingest.connectors.composio import verify_signature

    body = json.dumps({"probe": True}).encode()
    mac = base64.b64encode(
        hmac.new(secret.encode(), b"wh_probe.0." + body, hashlib.sha256).digest()
    ).decode()
    assert verify_signature(secret, "wh_probe", "0", body, f"v1,{mac}")
    console.print("✅ secret stored · signed sample verified locally")
    console.print(
        f"\nNext, in the Composio dashboard (composio.dev):\n"
        f"  1. connect the apps you want (GitHub, Gmail, Slack, …)\n"
        f"  2. enable their triggers\n"
        f"  3. set the webhook subscription URL to\n"
        f"     [bold]https://<your-tunnel>/v1/connectors/composio[/bold]\n"
        f"     (local port {port}; use cloudflared/ngrok/tailscale funnel)\n"
        f"  4. fire a test trigger and watch it in chief ui → History"
    )


def connect_github() -> None:
    import shutil

    _update_config(lambda cfg: cfg.setdefault("ingest", {}).update({"github": True}))
    if shutil.which("gh"):
        console.print("✅ github notifications poller enabled (5 min via `gh api`)")
    else:
        console.print(
            "✅ enabled — but [yellow]`gh` CLI not found[/yellow]: "
            "install it and run `gh auth login` before `chief run`"
        )


def connect_rss(url: str) -> None:
    def mutate(cfg):
        urls = cfg.setdefault("ingest", {}).setdefault("rss_urls", [])
        if url not in urls:
            urls.append(url)

    _update_config(mutate)
    console.print(f"✅ feed added — polled every 30 min: {url}")


def show_sources() -> None:
    from rich.table import Table

    from ingest.connectors import connector_status

    table = Table(title="sources")
    table.add_column("connector")
    table.add_column("status")
    table.add_column("")
    for s in connector_status():
        status = "[green]connected[/green]" if s["connected"] else "[dim]not configured[/dim]"
        table.add_row(s["name"], status, s["detail"])
    console.print(table)
