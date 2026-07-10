"""Step 20 acceptance: scripted wizard run (pexpect) on a clean HOME produces a
working config; install-service emits units; `chief run` wires everything."""

import stat
import sys
import tomllib

import pexpect
from typer.testing import CliRunner

from cli.main import app

runner = CliRunner()


def read_config(home):
    return tomllib.loads((home / "config.toml").read_text())


def test_wizard_defaults_flag_produces_working_config(tmp_path, monkeypatch):
    monkeypatch.setenv("CHIEF_HOME", str(tmp_path))
    result = runner.invoke(app, ["init", "--defaults"])
    assert result.exit_code == 0, result.output
    cfg = read_config(tmp_path)
    assert cfg["llm"]["backend"] in ("ollama", "deepseek", "anthropic", "openai", "fixtures")
    assert cfg["digest"]["times"] == ["08:00", "18:30"]
    assert cfg["quiet"]["hours"] == "23:00-08:00"
    assert "family" in cfg["quiet"]["whitelist"]
    assert cfg["context"]["foreground_app"] is False  # privacy default OFF
    assert (tmp_path / "POLICY.md").exists()
    assert (tmp_path / "USER.md").exists()


def test_wizard_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("CHIEF_HOME", str(tmp_path))
    assert runner.invoke(app, ["init", "--defaults"]).exit_code == 0
    (tmp_path / "POLICY.md").write_text("# POLICY\n## Muted topics\n- precious.rule\n")
    assert runner.invoke(app, ["init", "--defaults"]).exit_code == 0
    assert "precious.rule" in (tmp_path / "POLICY.md").read_text()  # never clobbers


def test_wizard_preserves_existing_connections_and_token(tmp_path, monkeypatch):
    monkeypatch.setenv("CHIEF_HOME", str(tmp_path))
    assert runner.invoke(app, ["init", "--defaults"]).exit_code == 0
    assert runner.invoke(
        app, ["connect", "rss", "--url", "https://example.com/feed"]
    ).exit_code == 0
    assert runner.invoke(
        app, ["connect", "composio", "--secret", "whsec_keep"]
    ).exit_code == 0
    before = read_config(tmp_path)

    assert runner.invoke(app, ["init", "--defaults"]).exit_code == 0
    after = read_config(tmp_path)

    assert after["ingest"]["rss_urls"] == ["https://example.com/feed"]
    assert after["connectors"]["composio"]["webhook_secret"] == "whsec_keep"
    assert after["ingest"]["webhook_token"] == before["ingest"]["webhook_token"]


def test_wizard_generates_private_config_and_token(tmp_path, monkeypatch):
    home = tmp_path / "chief-home"
    monkeypatch.setenv("CHIEF_HOME", str(home))

    assert runner.invoke(app, ["init", "--defaults"]).exit_code == 0

    cfg = read_config(home)
    assert cfg["ingest"]["webhook_token"] != "change-me"
    assert len(cfg["ingest"]["webhook_token"]) >= 32
    assert stat.S_IMODE(home.stat().st_mode) == 0o700
    for name in ("config.toml", "POLICY.md", "USER.md"):
        assert stat.S_IMODE((home / name).stat().st_mode) == 0o600


def test_wizard_blank_secret_answers_keep_existing_values(monkeypatch):
    from cli import init as wizard

    answers = wizard._answers_from_config(
        {
            "llm": {"backend": "deepseek", "api_key": "sk-keep"},
            "delivery": {
                "channels": ["telegram"],
                "telegram_token": "bot-keep",
                "chat_id": "42",
            },
        }
    )
    selections = iter(["deepseek", "telegram"])

    class Prompt:
        def __init__(self, answer):
            self.answer = answer

        def ask(self):
            return self.answer

    class Questionary:
        @staticmethod
        def select(*_args, **_kwargs):
            return Prompt(next(selections))

        @staticmethod
        def password(*_args, **_kwargs):
            return Prompt("")

        @staticmethod
        def text(message, *, default=""):
            return Prompt("" if message == "Chat id (blank to keep existing)" else default)

    monkeypatch.setitem(sys.modules, "questionary", Questionary)
    monkeypatch.setattr(wizard, "_gh_authed", lambda: False)

    updated = wizard._ask(answers)

    assert updated["api_key"] == "sk-keep"
    assert updated["telegram_token"] == "bot-keep"
    assert updated["chat_id"] == "42"


def test_wizard_interactive_all_enters(tmp_path):
    """SPEC §4.8: every question skippable — a human just pressing Enter wins."""
    child = pexpect.spawn(
        sys.executable,
        ["-m", "cli.main", "init"],
        env={"CHIEF_HOME": str(tmp_path), "PATH": "/usr/bin:/bin", "TERM": "dumb"},
        encoding="utf-8",
        timeout=30,
    )
    for _ in range(12):  # enough Enters for every question
        try:
            child.sendline("")
        except OSError:
            break
        try:
            child.expect("\n", timeout=3)
        except (pexpect.TIMEOUT, pexpect.EOF):
            break
    child.expect(pexpect.EOF, timeout=20)
    child.close()
    cfg = read_config(tmp_path)
    assert cfg["digest"]["times"] == ["08:00", "18:30"]


def test_install_service_emits_unit(tmp_path, monkeypatch):
    monkeypatch.setenv("CHIEF_HOME", str(tmp_path))
    result = runner.invoke(app, ["install-service"])
    assert result.exit_code == 0
    unit = tmp_path / "chief.service"
    assert unit.exists()
    text = unit.read_text()
    assert "chief run" in text or "cli.main run" in text
    assert "systemctl" in result.output  # instructions printed


def test_chief_run_smoke_once(tmp_path, monkeypatch):
    monkeypatch.setenv("CHIEF_HOME", str(tmp_path))
    assert runner.invoke(app, ["init", "--defaults"]).exit_code == 0
    result = runner.invoke(app, ["run", "--once"])
    assert result.exit_code == 0, result.output
    assert "chief is up" in result.output
