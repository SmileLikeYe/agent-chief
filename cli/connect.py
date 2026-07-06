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

from core.config import chief_home, config_path, load_config

console = Console(soft_wrap=True)  # never wrap URLs


def _serialize(cfg: dict) -> str:
    def value(v):
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, int | float):
            return str(v)
        if isinstance(v, list):
            return "[" + ", ".join(json.dumps(i) for i in v) + "]"
        return json.dumps(v)

    lines: list[str] = []
    for section, body in cfg.items():
        scalars = {k: v for k, v in body.items() if not isinstance(v, dict)}
        tables = {k: v for k, v in body.items() if isinstance(v, dict)}
        if scalars or not tables:
            lines.append(f"[{section}]")
            lines += [f"{k} = {value(v)}" for k, v in scalars.items()]
            lines.append("")
        for sub, subbody in tables.items():
            lines.append(f"[{section}.{sub}]")
            lines += [f"{k} = {value(v)}" for k, v in subbody.items()]
            lines.append("")
    return "\n".join(lines)


def _update_config(mutate) -> dict:
    path = config_path()
    cfg = tomllib.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    mutate(cfg)
    chief_home().mkdir(parents=True, exist_ok=True)
    path.write_text(_serialize(cfg), encoding="utf-8")
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
