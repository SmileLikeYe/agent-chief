"""Step 20 acceptance: scripted wizard run (pexpect) on a clean HOME produces a
working config; install-service emits units; `chief run` wires everything."""

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
