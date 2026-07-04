"""Step 23 acceptance guards: README quickstart + protocol completeness."""

from pathlib import Path

ROOT = Path(__file__).parent.parent
README = (ROOT / "README.md").read_text(encoding="utf-8")
PROTOCOL = (ROOT / "docs" / "protocol.md").read_text(encoding="utf-8")


def test_readme_has_hook_and_quickstart():
    assert "chief of staff" in README
    assert "uvx agent-chief demo" in README
    assert "demo.gif" in README  # GIF placeholder


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
