"""Calibration eval tests (SPEC v3.x Step 40): the routing score is measured for
discrimination (AUC) and calibration (ECE) against the cohort's hidden
preferences, deterministically. Pin the figures the docs cite."""

from typer.testing import CliRunner

from eval.calibration import auc, run_calibration

_CACHE: dict = {}


async def _report():
    if "r" not in _CACHE:
        _CACHE["r"] = await run_calibration()
    return _CACHE["r"]


# --- the AUC primitive (assumption-free, so worth a unit test) ----------------


def test_auc_is_rank_order_with_tie_handling():
    assert auc([(0.9, True), (0.1, False)]) == 1.0  # perfect
    assert auc([(0.1, True), (0.9, False)]) == 0.0  # inverted
    assert auc([(0.5, True), (0.5, False)]) == 0.5  # a tie averages to chance
    assert auc([(0.5, True)]) != auc([(0.5, True)])  # nan (no negatives) — nan != nan


# --- the benchmark ------------------------------------------------------------


async def test_scored_on_the_full_held_out_cohort_stream():
    report = await _report()
    assert report.n_events == 7200  # 100 users · 12 topics · 6 held-out events
    assert 0.4 < report.frac_wanted < 0.5  # both classes well represented


async def test_learning_inverts_a_backwards_salience_score():
    """The headline finding: raw salience is *anti*-correlated with what users
    want (loud newsletters, quiet incidents), so it ranks BELOW chance — and
    preference learning flips it into a strong discriminator."""
    report = await _report()
    assert report.auc_before < 0.5  # salience alone ranks backwards
    assert report.auc_after > 0.9  # learning makes the score discriminative
    assert report.auc_after - report.auc_before > 0.5


async def test_reliability_is_monotone_and_isotonic_calibrates():
    report = await _report()
    assert report.monotone  # P(wanted) never falls as the score rises
    # a parameter-free monotone map (fit on half, scored on the other) calibrates
    assert report.ece_isotonic < report.ece_raw
    assert report.ece_isotonic < 0.05


async def test_scene_thresholds_trade_recall_for_precision():
    """Higher scene bars must not lose precision and must shed recall — that's the
    whole point of a per-scene operating point."""
    report = await _report()
    ops = sorted(report.operating_points, key=lambda o: o.threshold)
    assert all(o.precision >= 0.9 for o in ops)
    # recall is (weakly) non-increasing as the interrupt bar rises
    recalls = [o.recall for o in ops]
    assert recalls[-1] < recalls[0]
    assert all(a >= b - 1e-9 for a, b in zip(recalls, recalls[1:], strict=False))


async def test_calibration_is_deterministic():
    a = await run_calibration()
    b = await run_calibration()
    assert (a.auc_after, a.ece_raw, a.ece_isotonic) == (b.auc_after, b.ece_raw, b.ece_isotonic)


async def test_published_numbers_are_pinned():
    report = await _report()
    assert round(report.auc_before, 3) == 0.368
    assert round(report.auc_after, 3) == 0.918
    assert round(report.ece_raw, 3) == 0.263
    assert report.ece_isotonic < 0.03


# --- report + CLI -------------------------------------------------------------


async def test_markdown_states_auc_ece_and_honesty():
    from eval.calibration import render_markdown

    md = render_markdown(await _report())
    assert "AUC" in md
    assert "Reliability" in md
    assert "Per-scene operating points" in md
    assert "Method & honesty" in md


def test_cli_eval_calibration_writes_report(tmp_path):
    from cli.main import app

    result = CliRunner().invoke(app, ["eval", "--calibration", "--out", str(tmp_path)])
    assert result.exit_code == 0, result.output
    report = tmp_path / "calibration.md"
    assert report.exists()
    assert "calibration" in report.read_text(encoding="utf-8").lower()
