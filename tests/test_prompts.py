"""Step 27 acceptance (SPEC v3.1): versioned Jinja2 prompt templates.

- all prompts live in judge/templates/<version>/*.j2;
- prompt version is stamped into every judged Decision's audit record;
- changing one word in a template yields a compare report with flipped samples.
"""

import json

from core.state import AuditLog, State
from eval.runner import render_compare_markdown, run_compare
from judge import prompts
from tests.helpers import StaticJudge, make_brain

PAYLOAD = {
    "source": "ci",
    "topic": "dev.ci",
    "summary": "CI failed on main: fixture drift in test_auth_flow",
}


# --- template rendering ---------------------------------------------------------


def test_templates_render_the_canonical_prompts():
    assert prompts.SYSTEM_PROMPT.startswith("You are the gatekeeper")
    assert "do not disturb" in prompts.SYSTEM_PROMPT
    assert prompts.render("system") == prompts.SYSTEM_PROMPT
    assert "ONLY the JSON object" in prompts.render("retry")


def test_all_prompt_templates_exist_for_v1():
    for name in ("system", "retry", "context", "user", "verify", "distill", "topic_infer"):
        assert prompts.template_exists(name, version="v1")


def test_parameterized_templates_take_variables():
    v = prompts.verify_prompt(acceptance="tests pass", result="218 passed")
    assert "tests pass" in v and "218 passed" in v
    d = prompts.distill_prompt(date="2026-07-05", changes="dev.ci urgency +0.1")
    assert "2026-07-05" in d and "{rule}" in d  # literal placeholder survives
    t = prompts.topic_infer_prompt(summary="CI failed on main")
    assert "CI failed on main" in t


def test_available_versions_lists_v1():
    assert "v1" in prompts.available_versions()


def test_version_and_root_overrides(tmp_path):
    (tmp_path / "v9").mkdir()
    (tmp_path / "v9" / "system.j2").write_text("MARKER prompt", encoding="utf-8")
    assert prompts.render("system", version="v9", root=tmp_path) == "MARKER prompt"


# --- version stamped in the audit log ---------------------------------------------


async def test_prompt_version_lands_in_audit_log(tmp_path):
    audit_path = tmp_path / "audit.jsonl"
    async with State.open(tmp_path / "s.db") as state:
        brain = make_brain(
            state, tmp_path, judge=StaticJudge(), audit=AuditLog(audit_path)
        )
        await brain.process(dict(PAYLOAD))
    line = json.loads(audit_path.read_text(encoding="utf-8").splitlines()[-1])
    assert line["prompt_version"] == prompts.PROMPT_VERSION


# --- eval --compare: one changed word flips samples ---------------------------------


class PromptSensitiveJudge:
    """Test double: reads its own rendered system template like a real backend."""

    def __init__(self, version: str, root):
        self.name = f"sensitive-{version}"
        self.prompt_version = version
        self._root = root

    async def judge(self, event, context):
        from judge.base import JudgeResult

        system = prompts.render("system", version=self.prompt_version, root=self._root)
        s = 0.62 if "URGENT" in system else 0.42  # one word changes the verdict
        return JudgeResult(
            urgency=s, relevance=s, actionability=s, novelty=s, confidence=s,
            reason="prompt-sensitive double",
        )


def _two_versions(tmp_path):
    for version, word in (("v1", "calm"), ("v2", "URGENT")):
        d = tmp_path / version
        d.mkdir()
        (d / "system.j2").write_text(f"Be {word} about events.", encoding="utf-8")
    return tmp_path


def test_compare_reports_delta_and_flipped_samples(tmp_path):
    root = _two_versions(tmp_path)
    report = run_compare(
        PromptSensitiveJudge("v1", root), PromptSensitiveJudge("v2", root)
    )
    assert report.flipped  # the one-word change flips routes on some cases
    assert report.a.agreement != report.b.agreement
    md = render_compare_markdown(report)
    assert "delta" in md.lower()
    first_flip = report.flipped[0]
    assert first_flip[0].event["id"] in md  # flipped sample ids are listed


def test_cli_eval_compare_writes_diff_report(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from cli.main import app

    result = CliRunner().invoke(
        app, ["eval", "--compare", "v1", "v1", "--out", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output
    reports = list(tmp_path.glob("compare-*.md"))
    assert len(reports) == 1
    text = reports[0].read_text(encoding="utf-8")
    assert "delta" in text.lower()
