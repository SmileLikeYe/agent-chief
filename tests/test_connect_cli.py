"""Step 35 acceptance (SPEC v3.2): chief connect / chief sources."""

import tomllib

from typer.testing import CliRunner

runner = CliRunner()


def config_at(tmp_path):
    return tomllib.loads((tmp_path / "config.toml").read_text(encoding="utf-8"))


def test_connect_composio_writes_secret_and_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("CHIEF_HOME", str(tmp_path))
    from cli.main import app

    result = runner.invoke(app, ["connect", "composio", "--secret", "whsec_1"])
    assert result.exit_code == 0, result.output
    assert config_at(tmp_path)["connectors"]["composio"]["webhook_secret"] == "whsec_1"
    assert "/v1/connectors/composio" in result.output  # tells the user the endpoint

    result = runner.invoke(app, ["connect", "composio", "--secret", "whsec_2"])
    assert result.exit_code == 0
    assert config_at(tmp_path)["connectors"]["composio"]["webhook_secret"] == "whsec_2"


def test_connect_composio_verifies_a_signed_sample(tmp_path, monkeypatch):
    monkeypatch.setenv("CHIEF_HOME", str(tmp_path))
    from cli.main import app

    result = runner.invoke(app, ["connect", "composio", "--secret", "whsec_x"])
    assert "signed sample verified" in result.output.lower()


def test_connect_rss_and_github(tmp_path, monkeypatch):
    monkeypatch.setenv("CHIEF_HOME", str(tmp_path))
    from cli.main import app

    result = runner.invoke(app, ["connect", "rss", "--url", "https://hnrss.org/frontpage"])
    assert result.exit_code == 0, result.output
    assert config_at(tmp_path)["ingest"]["rss_urls"] == ["https://hnrss.org/frontpage"]

    # appending a second url keeps the first
    runner.invoke(app, ["connect", "rss", "--url", "https://example.com/feed"])
    assert len(config_at(tmp_path)["ingest"]["rss_urls"]) == 2

    result = runner.invoke(app, ["connect", "github"])
    assert result.exit_code == 0
    assert config_at(tmp_path)["ingest"]["github"] is True


def test_connect_preserves_existing_config(tmp_path, monkeypatch):
    monkeypatch.setenv("CHIEF_HOME", str(tmp_path))
    (tmp_path / "config.toml").write_text(
        '[llm]\nbackend = "deepseek"\napi_key = "sk-keep-me"\n', encoding="utf-8"
    )
    from cli.main import app

    runner.invoke(app, ["connect", "composio", "--secret", "s"])
    cfg = config_at(tmp_path)
    assert cfg["llm"]["api_key"] == "sk-keep-me"  # untouched
    assert cfg["connectors"]["composio"]["webhook_secret"] == "s"


def test_sources_command_reflects_connections(tmp_path, monkeypatch):
    monkeypatch.setenv("CHIEF_HOME", str(tmp_path))
    from cli.main import app

    out = runner.invoke(app, ["sources"]).output
    assert "composio" in out and "not configured" in out

    runner.invoke(app, ["connect", "composio", "--secret", "s"])
    out = runner.invoke(app, ["sources"]).output
    assert "connected" in out


def test_connect_unknown_source_fails_cleanly(tmp_path, monkeypatch):
    monkeypatch.setenv("CHIEF_HOME", str(tmp_path))
    from cli.main import app

    result = runner.invoke(app, ["connect", "carrier-pigeon"])
    assert result.exit_code != 0
