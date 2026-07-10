"""Implements SPEC §4.8: onboarding wizard — every question skippable with
sensible defaults; generates ~/.chief/config.toml + POLICY.md + USER.md."""

import copy
import secrets
import shutil
import subprocess
from pathlib import Path

from rich.console import Console

from core.config import (
    UnsupportedConfig,
    config_path,
    ensure_private_home,
    load_config,
    policy_path,
    serialize_config,
    user_md_path,
    write_private_text,
)

console = Console()

DEFAULTS = {
    "backend": "fixtures",
    "model": "",
    "api_key": "",
    "channels": ["desktop"],
    "telegram_token": "",
    "chat_id": "",
    "digest_times": ["08:00", "18:30"],
    "quiet_hours": "23:00-08:00",
    "whitelist": ["family", "production_incident"],
    "github": False,
    "rss_urls": [],
    "workdir": "~/work",
    "dispatch_enabled": True,
    "foreground_app": False,
    "webhook_token": "",
    "webhook_port": 8787,
}


def _ollama_available() -> bool:
    return shutil.which("ollama") is not None


def _gh_authed() -> bool:
    if not shutil.which("gh"):
        return False
    try:
        return (
            subprocess.run(
                ["gh", "auth", "status"], capture_output=True, timeout=10, check=False
            ).returncode
            == 0
        )
    except Exception:
        return False


def _ask(answers: dict) -> dict:
    import questionary

    backend_default = answers["backend"]
    backend = questionary.select(
        "LLM backend (Enter for default)",
        choices=["ollama", "deepseek", "anthropic", "openai", "fixtures"],
        default=backend_default,
    ).ask()
    if backend is None:
        return answers  # non-interactive session: keep defaults
    answers["backend"] = backend
    if backend not in ("ollama", "fixtures"):
        api_key = questionary.password(
            f"{backend} API key (blank to keep existing)"
        ).ask()
        if api_key:
            answers["api_key"] = api_key

    channel = questionary.select(
        "Delivery channel",
        choices=["desktop", "telegram", "terminal"],
        default=answers["channels"][0],
    ).ask()
    answers["channels"] = [channel or "desktop"]
    if channel == "telegram":
        console.print("30s guide: https://core.telegram.org/bots#how-do-i-create-a-bot")
        telegram_token = questionary.password("Bot token (blank to keep existing)").ask()
        chat_id = questionary.text("Chat id (blank to keep existing)").ask()
        if telegram_token:
            answers["telegram_token"] = telegram_token
        if chat_id:
            answers["chat_id"] = chat_id

    current_times = ", ".join(answers["digest_times"])
    times = questionary.text("Digest times", default=current_times).ask() or current_times
    answers["digest_times"] = [t.strip() for t in times.split(",") if t.strip()]

    answers["quiet_hours"] = (
        questionary.text("Quiet hours", default=answers["quiet_hours"]).ask()
        or answers["quiet_hours"]
    )
    whitelist = (
        questionary.text(
            "Night whitelist topics", default=", ".join(answers["whitelist"])
        ).ask()
        or ", ".join(answers["whitelist"])
    )
    answers["whitelist"] = [w.strip() for w in whitelist.split(",") if w.strip()]

    if _gh_authed():
        answers["github"] = bool(
            questionary.confirm(
                "gh is authenticated — watch GitHub notifications?", default=answers["github"]
            )
            .ask()
        )
    rss_default = ", ".join(answers["rss_urls"])
    rss = questionary.text("RSS URLs (comma-separated, blank to skip)", default=rss_default).ask()
    answers["rss_urls"] = [url.strip() for url in (rss or "").split(",") if url.strip()]
    return answers


def _answers_from_config(config: dict) -> dict:
    answers = copy.deepcopy(DEFAULTS)
    llm = config.get("llm", {})
    delivery = config.get("delivery", {})
    digest = config.get("digest", {})
    quiet = config.get("quiet", {})
    dispatch = config.get("dispatch", {})
    context = config.get("context", {})
    ingest = config.get("ingest", {})
    answers.update(
        backend=llm.get("backend", answers["backend"]),
        model=llm.get("model", answers["model"]),
        api_key=llm.get("api_key", answers["api_key"]),
        channels=delivery.get("channels", answers["channels"]),
        telegram_token=delivery.get("telegram_token", answers["telegram_token"]),
        chat_id=delivery.get("chat_id", answers["chat_id"]),
        digest_times=digest.get("times", answers["digest_times"]),
        quiet_hours=quiet.get("hours", answers["quiet_hours"]),
        whitelist=quiet.get("whitelist", answers["whitelist"]),
        workdir=dispatch.get("claude_code_workdir", answers["workdir"]),
        dispatch_enabled=dispatch.get("enabled", answers["dispatch_enabled"]),
        foreground_app=context.get("foreground_app", answers["foreground_app"]),
        github=ingest.get("github", answers["github"]),
        rss_urls=ingest.get("rss_urls", answers["rss_urls"]),
        webhook_token=ingest.get("webhook_token", answers["webhook_token"]),
        webhook_port=ingest.get("webhook_port", answers["webhook_port"]),
    )
    return answers


def _managed_config(a: dict) -> dict:
    return {
        "llm": {"backend": a["backend"], "model": a["model"], "api_key": a["api_key"]},
        "delivery": {
            "channels": a["channels"],
            "telegram_token": a["telegram_token"],
            "chat_id": a["chat_id"],
        },
        "digest": {"times": a["digest_times"]},
        "quiet": {"hours": a["quiet_hours"], "whitelist": a["whitelist"]},
        "dispatch": {
            "claude_code_workdir": a["workdir"],
            "enabled": a["dispatch_enabled"],
        },
        "context": {"foreground_app": a["foreground_app"]},
        "ingest": {
            "github": a["github"],
            "rss_urls": a["rss_urls"],
            "webhook_token": a["webhook_token"],
            "webhook_port": a["webhook_port"],
        },
    }


def _merge_config(existing: dict, managed: dict) -> dict:
    merged = copy.deepcopy(existing)
    for section, values in managed.items():
        current = merged.setdefault(section, {})
        if not isinstance(current, dict):
            current = merged[section] = {}
        current.update(values)
    return merged


def _template(name: str) -> str:
    return (Path(__file__).parent.parent / "policy" / name).read_text(encoding="utf-8")


def run_wizard(defaults_only: bool = False) -> Path:
    ensure_private_home()
    existing = load_config()

    answers = _answers_from_config(existing)
    if not existing and _ollama_available():
        answers["backend"] = "ollama"
    elif not existing and not defaults_only:
        answers["backend"] = "deepseek"
    if not defaults_only:
        answers = _ask(answers)
    if answers["webhook_token"] in ("", "change-me"):
        answers["webhook_token"] = secrets.token_urlsafe(32)

    merged = _merge_config(existing, _managed_config(answers))
    try:
        rendered = serialize_config(merged)
    except UnsupportedConfig as exc:
        raise SystemExit(
            f"chief init can't safely rewrite {config_path()} ({exc}). "
            "Keep the existing config and edit it by hand."
        ) from exc
    write_private_text(config_path(), rendered)
    if not policy_path().exists():  # never clobber user edits
        write_private_text(policy_path(), _template("POLICY.template.md"))
    if not user_md_path().exists():
        write_private_text(user_md_path(), _template("USER.template.md"))

    console.print(f"✅ wrote {config_path()}")
    if answers["backend"] == "fixtures":
        console.print(
            "[yellow]fixtures is demo-only[/yellow] — run [bold]chief init[/bold] "
            "and choose Ollama or a hosted backend before starting real sources"
        )
    else:
        console.print("Next: [bold]chief run[/bold] (or [bold]chief install-service[/bold])")
    console.print("Webhook token for integrations: [bold]chief token[/bold]")
    return config_path()


def install_service() -> Path:
    """Emit a systemd user unit (Linux) / launchd plist (macOS) into ~/.chief."""
    import platform
    import sys

    home = ensure_private_home()
    chief_bin = shutil.which("chief")
    exec_cmd = chief_bin + " run" if chief_bin else f"{sys.executable} -m cli.main run"

    if platform.system() == "Darwin":
        path = home / "com.chief.agent.plist"
        args = "".join(f"<string>{p}</string>" for p in exec_cmd.split())
        path.write_text(
            f"""<?xml version="1.0" encoding="UTF-8"?>
<plist version="1.0"><dict>
  <key>Label</key><string>com.chief.agent</string>
  <key>ProgramArguments</key><array>{args}</array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
</dict></plist>
""",
            encoding="utf-8",
        )
        console.print(f"wrote {path}\nInstall: launchctl load {path}")
    else:
        path = home / "chief.service"
        path.write_text(
            f"""[Unit]
Description=chief — the chief of staff for your agents

[Service]
ExecStart={exec_cmd}
Restart=on-failure

[Install]
WantedBy=default.target
""",
            encoding="utf-8",
        )
        console.print(
            f"wrote {path}\n"
            f"Install: mkdir -p ~/.config/systemd/user && cp {path} ~/.config/systemd/user/ "
            "&& systemctl --user enable --now chief"
        )
    return path
