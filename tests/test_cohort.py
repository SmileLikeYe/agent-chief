"""Cohort preference-learning benchmark tests (SPEC v3.2 Step 38): the reward
loop trains a *population*, deterministically, and the report is honest about
who it can't teach."""

from typer.testing import CliRunner

from eval.cohort import (
    load_cohort,
    reachable,
    render_markdown,
    run_cohort,
)
from eval.generate_personas import build

# run_cohort is deterministic and ~5s; compute once and share across the
# read-only assertions below (the determinism test still runs it fresh twice).
_CACHE: dict = {}


async def _report():
    if "r" not in _CACHE:
        _CACHE["r"] = await run_cohort()
    return _CACHE["r"]


# --- the committed dataset ---------------------------------------------------


def test_personas_file_is_exactly_what_the_generator_emits():
    """The committed personas.jsonl must be reproducible from the seed — else
    the benchmark numbers below drift silently."""
    meta_gen, personas_gen = build()
    meta_file, personas_file = load_cohort()
    assert meta_file == meta_gen
    assert personas_file == personas_gen


def test_cohort_is_100_well_formed_users():
    meta, personas = load_cohort()
    assert meta["n"] == 100 and len(personas) == 100
    topics = {t["topic"] for t in meta["topics"]}
    for p in personas:
        assert {"id", "scene", "noise_tier", "feedback_noise", "wants_interrupt"} <= p.keys()
        wants = set(p["wants_interrupt"])
        assert wants <= topics
        # both classes present so precision/recall and agreement are well-defined
        assert 1 <= len(wants) < len(topics)


def test_reachability_math():
    # 5·min(.5,s)·s ≥ T. idle bar 0.45: s=0.44 → 5·.44·.44=0.968 ≥ .45 (reachable)
    assert reachable(0.44, 0.45)
    # meeting bar 0.90: a quiet 0.34 topic → 5·.34·.34=0.578 < .90 (unreachable)
    assert not reachable(0.34, 0.90)


# --- the benchmark -----------------------------------------------------------


async def test_cohort_learns_across_the_population():
    report = await _report()
    assert report.n == 100
    # held-out interrupt quality jumps from near-useless to strong
    assert report.f1_before < 0.3
    assert report.f1_after > 0.7
    # a real majority converge, but not everyone (the ceiling is real)
    assert 0.5 <= report.converged_frac < 1.0


async def test_mean_curve_rises_and_never_regresses():
    report = await _report()
    curve = report.mean_curve
    assert curve[-1] > curve[0] + 0.3
    # each persona's curve is monotonic by construction → so is the cohort mean
    assert all(a <= b + 1e-9 for a, b in zip(curve, curve[1:], strict=False))


async def test_convergence_is_exactly_the_reachable_users():
    """The honest self-consistency: a user converges (≥95%) iff preference can
    lift every wanted topic. One unreachable topic caps agreement at 11/12."""
    report = await _report()
    for r in report.converged:
        assert r.n_unreachable == 0
    for r in report.ceiling_capped:
        assert r.converged_round is None
        assert r.final < 0.95
    # partition: converged ∪ ceiling-capped == everyone
    assert len(report.converged) + len(report.ceiling_capped) == report.n


async def test_noise_degrades_convergence():
    """More erratic feedback → fewer users converge in the same rounds."""
    report = await _report()
    by = {tier: cf for tier, _n, cf, _b, _a in report.by_noise()}
    assert by["erratic"] <= by["clean"]  # highest noise no better than lowest


async def test_cohort_is_deterministic():
    a = await run_cohort()
    b = await run_cohort()
    assert [r.curve for r in a.results] == [r.curve for r in b.results]
    assert a.f1_after == b.f1_after


async def test_published_numbers_are_pinned():
    """The exact figures the README/blog cite — pin them so a scorer or persona
    change can't silently move a published claim (mirrors the learning eval)."""
    report = await _report()
    assert report.converged_frac == 0.64
    assert round(report.f1_before, 2) == 0.10
    assert round(report.f1_after, 2) == 0.81
    assert report.convergence_pct(0.50) == 3
    assert len(report.ceiling_capped) == 36


# --- report + CLI ------------------------------------------------------------


async def test_markdown_report_states_headline_and_ceiling():
    md = render_markdown(await _report())
    assert "users converge" in md
    assert "Held-out interrupt F1" in md
    assert "By feedback-noise tier" in md
    assert "The ceiling, stated" in md  # honesty section is not optional


def test_cli_eval_cohort_writes_report(tmp_path):
    from cli.main import app

    result = CliRunner().invoke(app, ["eval", "--cohort", "--out", str(tmp_path)])
    assert result.exit_code == 0, result.output
    report = tmp_path / "cohort.md"
    assert report.exists()
    assert "cohort" in report.read_text(encoding="utf-8").lower()
