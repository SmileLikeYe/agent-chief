"""Step 29 acceptance (SPEC v3.1): dual skill packaging + chief lite.

- both SKILL.md files (openclaw + claude-code) lint clean;
- `chief lite` is judgment-only: stages 1-3 + routing, no learner, no daemon,
  works standalone with minimal setup (zero-config → conservative fallback).
"""

import json
from pathlib import Path

from typer.testing import CliRunner

ROOT = Path(__file__).parent.parent
SKILLS = {
    "openclaw": ROOT / "skills" / "openclaw" / "SKILL.md",
    "claude-code": ROOT / "skills" / "claude-code" / "SKILL.md",
}


# --- skill lint (both hosts) ---------------------------------------------------


def test_both_skill_files_have_frontmatter():
    for host, path in SKILLS.items():
        text = path.read_text(encoding="utf-8")
        assert text.startswith("---\n"), f"{host}: missing frontmatter"
        fm = text.split("---", 2)[1]
        assert "name:" in fm and "description:" in fm, f"{host}: frontmatter incomplete"


def test_both_skills_forbid_direct_messaging():
    for host, path in SKILLS.items():
        text = path.read_text(encoding="utf-8")
        assert "MUST NOT" in text, f"{host}: missing the no-direct-messaging rule"
        assert "propose" in text.lower() or "chief lite" in text.lower()


def test_claude_code_skill_documents_lite_mode():
    text = SKILLS["claude-code"].read_text(encoding="utf-8")
    assert "chief lite" in text
    assert "drop" in text and "digest" in text  # explains obeying routes


def test_manual_test_transcripts_documented():
    doc = (ROOT / "docs" / "skill-manual-tests.md").read_text(encoding="utf-8")
    for host in ("openclaw", "claude-code"):
        assert host in doc.lower()
    assert "chief lite" in doc


# --- chief lite ------------------------------------------------------------------


def _lite(monkeypatch, tmp_path, payload):
    monkeypatch.setenv("CHIEF_HOME", str(tmp_path))
    from cli.main import app

    result = CliRunner().invoke(app, ["lite", json.dumps(payload)])
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


def test_lite_drops_zero_information(tmp_path, monkeypatch):
    decision = _lite(
        monkeypatch, tmp_path,
        {"source": "hb", "topic": "ops.heartbeat",
         "summary": "Heartbeat: all clear, nothing to report"},
    )
    assert decision["route"] == "drop"
    assert decision["stage"] == 1


def test_lite_zero_config_is_conservative_not_crashy(tmp_path, monkeypatch):
    # no config.toml → fixtures backend knows nothing. The guarantee is
    # "conservative, never crashes": a borderline event is held (digest), never
    # escalated to interrupt. HOW it's held is time-dependent and both are
    # correct — degraded-digest by day, quiet-hours-digest at night — so assert
    # the guarantee, not the mechanism (which would flake across midnight).
    decision = _lite(
        monkeypatch, tmp_path,
        {"source": "agent", "topic": "dev.ci", "summary": "CI failed on main"},
    )
    assert decision["route"] in ("digest", "drop")
    assert decision["route"] != "interrupt"


def test_lite_reads_stdin(tmp_path, monkeypatch):
    monkeypatch.setenv("CHIEF_HOME", str(tmp_path))
    from cli.main import app

    payload = json.dumps({"source": "a", "topic": "ops.heartbeat",
                          "summary": "Nightly check complete, everything all good."})
    result = CliRunner().invoke(app, ["lite"], input=payload)
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["route"] == "drop"


def test_lite_is_stateless_no_learner_no_daemon(tmp_path, monkeypatch):
    # same event twice: no dedup carryover because lite keeps no state
    payload = {"source": "a", "topic": "dev.ci", "summary": "CI failed on main",
               "dedup_key": "same"}
    first = _lite(monkeypatch, tmp_path, payload)
    second = _lite(monkeypatch, tmp_path, payload)
    assert first["route"] == second["route"]  # not turned into a dedup drop
