"""Ablation eval tests (SPEC v3.x Step 39): each funnel stage is *measured* to
earn its keep on the golden 200, deterministically. Pin the published figures so
a scorer/dataset change can't silently move a claim the README/blog cites."""

from typer.testing import CliRunner

from eval.ablation import per_call_usd, render_markdown, run_ablation

_CACHE: dict = {}


async def _report():
    if "r" not in _CACHE:
        _CACHE["r"] = await run_ablation()
    return _CACHE["r"]


# --- the sweep ---------------------------------------------------------------


async def test_full_funnel_is_the_baseline_and_agrees_perfectly():
    """The golden labels were authored through the full pipeline, so the full
    funnel must reproduce them exactly — the anchor every delta is measured from."""
    report = await _report()
    assert report.n == 200
    assert report.full.agreement == 1.0
    assert report.full.judge_calls == 141  # 200 − 59 stage-1 resolutions


async def test_stage1_pays_on_both_axes():
    """Removing stage-1 sends the 59 rule-resolved events to the judge: more
    paid calls AND worse routing (the judge can't see mute/dedup/clock state)."""
    report = await _report()
    no_s1 = report.runs["no_stage1"]
    assert no_s1.judge_calls == 200
    assert report.stage1_calls_saved == 59  # 200 − 141
    # accuracy strictly worse without the hard rules
    assert no_s1.agreement < report.full.agreement
    assert report.stage1_accuracy_delta > 0.15


async def test_judge_lifts_far_above_the_rules_only_floor():
    """−judge is production's degraded mode: rule hit, else conservative digest.
    The judge must add real discretion on top of the rules, not ride on them."""
    report = await _report()
    rules_only = report.runs["no_judge"]
    assert rules_only.judge_calls == 0
    assert 0.5 < rules_only.agreement < report.full.agreement
    assert report.judge_accuracy_delta > 0.3


async def test_stage2_is_a_cost_cache_not_an_accuracy_stage():
    """Warm cache: near-free on repeat traffic, faithful (not lossless) routing."""
    report = await _report()
    assert report.warm_baseline_calls == 141  # no cache
    assert report.warm_first_calls < report.warm_baseline_calls  # helps in one pass
    assert report.warm_second_calls == 0  # identical traffic → all cached
    assert report.warm_second_hits == 141
    # a cache trades at most a hair of agreement for erasing every judge call
    assert report.warm_second_agreed >= report.n - 2


async def test_cost_scales_exactly_with_judge_calls():
    report = await _report()
    assert per_call_usd() > 0  # nominal DeepSeek tokens are priced
    assert report.cost_ratio("full") == 1.0
    assert report.cost_ratio("no_judge") == 0.0
    assert round(report.cost_ratio("no_stage1"), 2) == round(200 / 141, 2)


async def test_ablation_is_deterministic():
    a = await run_ablation()
    b = await run_ablation()
    assert {k: v.judge_calls for k, v in a.runs.items()} == {
        k: v.judge_calls for k, v in b.runs.items()
    }
    assert a.warm_second_calls == b.warm_second_calls


async def test_published_numbers_are_pinned():
    """The exact figures docs/eval/ablation.md and the README cite."""
    report = await _report()
    assert report.full.judge_calls == 141
    assert report.runs["no_stage1"].agreement == 0.80
    assert round(report.runs["no_judge"].agreement, 3) == 0.615
    assert report.stage1_calls_saved == 59
    assert round(report.stage1_accuracy_delta, 2) == 0.20
    assert round(report.judge_accuracy_delta, 3) == 0.385


# --- report + CLI ------------------------------------------------------------


async def test_markdown_states_the_verdict_and_the_honesty_note():
    md = render_markdown(await _report())
    assert "does each funnel stage earn its keep" in md
    assert "Cold-path configurations" in md
    assert "warm cache" in md.lower()
    assert "Method & honesty" in md  # the assumptions are not hidden


def test_cli_eval_ablation_writes_report(tmp_path):
    from cli.main import app

    result = CliRunner().invoke(app, ["eval", "--ablation", "--out", str(tmp_path)])
    assert result.exit_code == 0, result.output
    report = tmp_path / "ablation.md"
    assert report.exists()
    assert "ablation" in report.read_text(encoding="utf-8").lower()
