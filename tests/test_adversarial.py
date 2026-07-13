"""Adversarial red-team tests (SPEC v3.x Step 41): Chief is a trust boundary, so
prove hostile input is contained — injection can't override a hard rule, prose
can't move the score, malformed payloads fail closed, the executor can't be
shell-escaped, and untrusted text can't smuggle escapes to the terminal."""

import io

import httpx
import pytest

from eval.redteam import run_redteam

# --- the harness --------------------------------------------------------------


def test_every_attack_in_the_corpus_is_contained():
    report = run_redteam()
    assert report.breaches == []
    assert report.contained == report.total == 16
    assert len(report.categories) == 5


def test_a_mute_cannot_be_talked_past():
    """The headline property: a muted topic stays dropped even with a maxed judge
    verdict and a summary explicitly demanding the mute be overridden."""
    report = run_redteam()
    mute = next(r for r in report.results if r.id == "mute_override")
    assert mute.contained and "drop" in mute.outcome


def test_shell_metacharacters_stay_one_literal_argv_element():
    report = run_redteam()
    shell = [r for r in report.results if r.category == "executor_shell"]
    assert shell and all(r.contained for r in shell)


def test_each_category_fully_contained():
    report = run_redteam()
    for cat in report.categories:
        rows = [r for r in report.results if r.category == cat]
        assert all(r.contained for r in rows), cat


def test_report_states_the_verdict_and_scope():
    from eval.redteam import render_markdown

    md = render_markdown(run_redteam())
    assert "attacks contained" in md
    assert "SPEC §13" in md
    assert "does **not** claim the LLM judge" in md  # honest about scope


def test_cli_eval_redteam_passes_and_writes_report(tmp_path):
    from typer.testing import CliRunner

    from cli.main import app

    result = CliRunner().invoke(app, ["eval", "--redteam", "--out", str(tmp_path)])
    assert result.exit_code == 0, result.output  # a breach would exit 1
    report = tmp_path / "redteam.md"
    assert report.exists()
    assert "red-team" in report.read_text(encoding="utf-8").lower()


# --- the display sanitisation the red team motivated --------------------------


async def test_terminal_renders_markup_literally_and_strips_ansi():
    """An event summary must not be able to inject rich markup or ANSI escapes
    into the terminal: markup renders literally (Text), control bytes are gone."""
    from rich.console import Console

    from delivery.base import DeliveryMessage
    from delivery.terminal import TerminalChannel

    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, width=200)
    ch = TerminalChannel(console=console)
    payload = "[red]FAKE CRIT[/red] \x1b[31mred\x1b[0m\x07"
    await ch.send(
        DeliveryMessage(summary=payload, event_id="e", topic="t", plan=None, buttons=False),
        level="terminal",
    )
    out = buf.getvalue()
    assert "[red]FAKE CRIT[/red]" in out  # markup shown, NOT interpreted
    assert "\x1b" not in out and "\x07" not in out  # escape bytes stripped


def test_strip_control_keeps_newline_and_tab_only():
    from delivery.base import strip_control

    assert strip_control("a\x1b[31mb\x00c\x07") == "a[31mbc"
    assert strip_control("line1\nline2\tcol") == "line1\nline2\tcol"  # \n,\t preserved


# --- the HTTP ingest boundary (fail closed) -----------------------------------


@pytest.fixture
async def client(tmp_path):
    from core.state import State
    from ingest.http import create_app
    from tests.helpers import make_brain

    async with State.open(tmp_path / "s.db") as state:
        brain = make_brain(state, tmp_path)
        app = create_app(brain, token="sekrit")
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


async def test_ingest_rejects_an_oversized_summary(client):
    """A 20k-char summary is rejected at the schema (fail closed), not truncated
    into the pipeline."""
    payload = {"source": "attacker", "topic": "dev.ci", "summary": "A" * 20_000}
    resp = await client.post(
        "/v1/events", json=payload, headers={"Authorization": "Bearer sekrit"}
    )
    assert resp.status_code == 422


async def test_ingest_rejects_a_bad_bearer_token(client):
    resp = await client.post(
        "/v1/events", json={"source": "a", "topic": "t", "summary": "s"},
        headers={"Authorization": "Bearer wrong"},
    )
    assert resp.status_code == 401


async def test_composio_webhook_caps_body_size(tmp_path):
    """The tunnel-exposed connector endpoint rejects oversized bodies before
    buffering them (413), independent of the schema cap."""
    from core.state import State
    from ingest.http import create_app
    from tests.helpers import make_brain

    async with State.open(tmp_path / "s.db") as state:
        brain = make_brain(state, tmp_path)
        app = create_app(
            brain, token="sekrit", connectors={"composio": {"webhook_secret": "shh"}}
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            big = "x" * (1 << 21)  # 2 MiB > MAX_WEBHOOK_BYTES (1 MiB)
            resp = await c.post(
                "/v1/connectors/composio",
                content=big,
                headers={"content-type": "application/json"},
            )
            assert resp.status_code == 413
