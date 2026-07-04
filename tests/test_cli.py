"""Step 1 acceptance: `chief --help` lists all SPEC §5 subcommands."""

from typer.testing import CliRunner

from cli.main import app

runner = CliRunner()

SUBCOMMANDS = [
    "demo",
    "init",
    "run",
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
