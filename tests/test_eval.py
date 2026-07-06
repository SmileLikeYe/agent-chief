"""Step 25 acceptance (SPEC v3.1): golden dataset + eval harness.

- fixture backend scores 100% on the REGRESSION eval (the demo 24);
- a real backend produces a bucketed agreement report (capability eval);
- CI fails if regression < 100% (this file runs in CI).
"""

import json
from pathlib import Path

from typer.testing import CliRunner

from eval.runner import (
    GOLDEN_PATH,
    load_golden,
    render_markdown,
    run_capability,
    run_regression,
)
from tests.helpers import StaticJudge

ROUTES = {"interrupt", "digest", "dispatch", "curate", "drop"}


def test_regression_demo_is_100_percent_on_fixture_backend():
    report = run_regression()
    assert report.kind == "regression"
    assert report.total == 24
    assert report.agreement == 1.0
    assert report.mismatches == []


def test_golden_dataset_is_large_labeled_and_diverse():
    fixture = load_golden()
    entries = fixture.entries
    assert len(entries) >= 190  # "~200 labeled events"
    ids = [e.event["id"] for e in entries]
    assert len(ids) == len(set(ids))  # unique ids
    for e in entries:
        assert e.expected_route in ROUTES
        assert e.rationale  # one-line rationale on every case
    # diversity: all five routes and at least 5 scenes appear
    assert {e.expected_route for e in entries} == ROUTES
    assert len({e.scene["scene"] for e in entries}) >= 5


def test_golden_is_self_consistent_under_fixture_backend():
    # Labels were generated rule-first and verified against the pipeline;
    # the fixture backend is the sanity ceiling — it must agree ~fully.
    report = run_capability()
    assert report.kind == "capability"
    assert report.agreement == 1.0


def test_capability_report_is_bucketed_by_route_topic_scene():
    report = run_capability(judge=StaticJudge())  # a "real" backend stand-in
    assert 0.0 < report.agreement < 1.0  # a non-fixture judge diverges
    for bucket in ("route", "topic", "scene"):
        rows = report.buckets(bucket)
        assert rows, f"empty {bucket} buckets"
        for _name, agreed, total in rows:
            assert 0 <= agreed <= total


def test_markdown_report_renders_headline_and_buckets(tmp_path):
    report = run_capability(judge=StaticJudge())
    md = render_markdown(report)
    assert "agreement" in md.lower()
    assert f"{report.agreement:.1%}" in md
    for section in ("By route", "By topic", "By scene", "Mismatches"):
        assert section in md


def test_cli_eval_writes_report(tmp_path):
    from cli.main import app

    result = CliRunner().invoke(
        app, ["eval", "--backend", "fixtures", "--out", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output
    reports = list(tmp_path.glob("*.md"))
    assert len(reports) == 2  # regression + capability
    joined = " ".join(p.name for p in reports)
    assert "regression" in joined and "capability" in joined


def test_golden_jsonl_lines_are_valid_json():
    lines = Path(GOLDEN_PATH).read_text(encoding="utf-8").splitlines()
    meta = json.loads(lines[0])
    assert meta["type"] == "meta" and "policy" in meta
    for line in lines[1:]:
        case = json.loads(line)
        assert case["type"] == "case"
