"""Step 1 acceptance: `chief --help` lists all SPEC §5 subcommands."""

import tomllib

from typer.testing import CliRunner

from cli.main import app

runner = CliRunner()

SUBCOMMANDS = [
    "demo",
    "init",
    "run",
    "token",
    "ui",
    "digest",
    "status",
    "policy",
    "report",
    "install-service",
]


def test_help_lists_all_subcommands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in SUBCOMMANDS:
        assert cmd in result.output, f"missing subcommand: {cmd}"


def test_version_flag():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.output.startswith("chief ")


def test_token_prints_configured_webhook_token(tmp_path, monkeypatch):
    monkeypatch.setenv("CHIEF_HOME", str(tmp_path))
    assert runner.invoke(app, ["init", "--defaults"]).exit_code == 0
    expected = tomllib.loads((tmp_path / "config.toml").read_text(encoding="utf-8"))[
        "ingest"
    ]["webhook_token"]

    result = runner.invoke(app, ["token"])

    assert result.exit_code == 0
    assert result.output.strip() == expected
