"""Step 23 acceptance guards: README quickstart + protocol completeness."""

from pathlib import Path

ROOT = Path(__file__).parent.parent
README = (ROOT / "README.md").read_text(encoding="utf-8")
PROTOCOL = (ROOT / "docs" / "protocol.md").read_text(encoding="utf-8")
SEND_EVENT = (ROOT / "examples" / "send-event.sh").read_text(encoding="utf-8")
PYTHON_CLIENT = (ROOT / "examples" / "python_client.py").read_text(encoding="utf-8")
CI_WORKFLOW = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")


def test_readme_has_hook_and_quickstart():
    assert "chief of staff" in README
    assert "uvx agent-chief demo" in README
    assert "demo.gif" in README  # GIF placeholder


def test_real_sources_quickstart_uses_installed_cli_and_token_command():
    assert "uv tool install agent-chief" in README
    assert "uvx agent-chief init" not in README
    assert 'export CHIEF_TOKEN="$(chief token)"' in README


def test_examples_do_not_fall_back_to_public_default_token():
    assert "change-me" not in SEND_EVENT
    assert "change-me" not in PYTHON_CLIENT
    assert "chief token" in SEND_EVENT


def test_ci_runs_on_linux_and_macos():
    assert "ubuntu-latest" in CI_WORKFLOW
    assert "macos-latest" in CI_WORKFLOW
    assert "matrix.os" in CI_WORKFLOW


def test_readme_kill_all_clear_section():
    assert "all clear" in README.lower()
    assert "zero-information" in README.lower()


def test_readme_shadow_mode_trust_story():
    assert "Shadow mode" in README
    assert "Tact Report" in README


def test_protocol_is_self_sufficient():
    # a third party needs: endpoint, auth, required fields, a full example, responses
    assert "POST" in PROTOCOL and "/v1/events" in PROTOCOL
    assert "Authorization: Bearer" in PROTOCOL
    for field in ("source", "summary", "topic", "dedup_key", "claimed_urgency"):
        assert f"`{field}`" in PROTOCOL
    assert "curl -X POST" in PROTOCOL
    for route in ("interrupt", "digest", "dispatch", "curate", "drop"):
        assert route in PROTOCOL
    assert "401" in PROTOCOL and "422" in PROTOCOL
