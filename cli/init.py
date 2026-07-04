"""Implements SPEC §4.8: onboarding wizard — every question skippable with
sensible defaults; generates ~/.chief/config.toml + POLICY.md + USER.md."""

import shutil
import subprocess
from pathlib import Path

from rich.console import Console

from core.config import chief_home, config_path, policy_path, user_md_path

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

    backend_default = "ollama" if _ollama_available() else "deepseek"
    backend = questionary.select(
        "LLM backend (Enter for default)",
        choices=["ollama", "deepseek", "anthropic", "openai", "fixtures"],
        default=backend_default,
    ).ask()
    if backend is None:
        return answers  # non-interactive session: keep defaults
    answers["backend"] = backend
    if backend not in ("ollama", "fixtures"):
        answers["api_key"] = questionary.password(f"{backend} API key (blank to skip)").ask() or ""

    channel = questionary.select(
        "Delivery channel", choices=["desktop", "telegram", "terminal"], default="desktop"
    ).ask()
    answers["channels"] = [channel or "desktop"]
    if channel == "telegram":
        console.print("30s guide: https://core.telegram.org/bots#how-do-i-create-a-bot")
        answers["telegram_token"] = questionary.password("Bot token (blank to skip)").ask() or ""
        answers["chat_id"] = questionary.text("Chat id (blank to skip)").ask() or ""

    times = questionary.text("Digest times", default="08:00, 18:30").ask() or "08:00, 18:30"
    answers["digest_times"] = [t.strip() for t in times.split(",") if t.strip()]

    answers["quiet_hours"] = (
        questionary.text("Quiet hours", default="23:00-08:00").ask() or "23:00-08:00"
    )
    whitelist = (
        questionary.text("Night whitelist topics", default="family, production_incident").ask()
        or "family, production_incident"
    )
    answers["whitelist"] = [w.strip() for w in whitelist.split(",") if w.strip()]

    if _gh_authed():
        answers["github"] = bool(
            questionary.confirm("gh is authenticated — watch GitHub notifications?", default=True)
            .ask()
        )
    rss = questionary.text("RSS url to watch (blank to skip)", default="").ask() or ""
    answers["rss_urls"] = [rss.strip()] if rss.strip() else []
    return answers


def _render_config(a: dict) -> str:
    def toml_list(items: list[str]) -> str:
        return "[" + ", ".join(f'"{i}"' for i in items) + "]"

    return f"""# chief configuration (SPEC §10)
[llm]
backend = "{a["backend"]}"
model = "{a["model"]}"
api_key = "{a["api_key"]}"

[delivery]
channels = {toml_list(a["channels"])}
telegram_token = "{a["telegram_token"]}"
chat_id = "{a["chat_id"]}"

[digest]
times = {toml_list(a["digest_times"])}

[quiet]
hours = "{a["quiet_hours"]}"
whitelist = {toml_list(a["whitelist"])}

[dispatch]
claude_code_workdir = "{a["workdir"]}"
enabled = true

[context]
foreground_app = false  # privacy-sensitive, default OFF

[ingest]
github = {str(a["github"]).lower()}
rss_urls = {toml_list(a["rss_urls"])}
webhook_token = "change-me"
webhook_port = 8787
"""


def _template(name: str) -> str:
    return (Path(__file__).parent.parent / "policy" / name).read_text(encoding="utf-8")


def run_wizard(defaults_only: bool = False) -> Path:
    home = chief_home()
    home.mkdir(parents=True, exist_ok=True)

    answers = dict(DEFAULTS)
    if _ollama_available():
        answers["backend"] = "ollama"
    if not defaults_only:
        answers = _ask(answers)

    config_path().write_text(_render_config(answers), encoding="utf-8")
    if not policy_path().exists():  # never clobber user edits
        policy_path().write_text(_template("POLICY.template.md"), encoding="utf-8")
    if not user_md_path().exists():
        user_md_path().write_text(_template("USER.template.md"), encoding="utf-8")

    console.print(f"✅ wrote {config_path()}")
    console.print("Next: [bold]chief run[/bold] (or [bold]chief install-service[/bold])")
    return config_path()


def install_service() -> Path:
    """Emit a systemd user unit (Linux) / launchd plist (macOS) into ~/.chief."""
    import platform
    import sys

    home = chief_home()
    home.mkdir(parents=True, exist_ok=True)
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
