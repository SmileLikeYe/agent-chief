"""Preference-drift benchmark (Step 43): Chief tracks a moving target and lets go
of pins it over-learned. Deterministic — the numbers here are the published ones."""

from eval.drift import render_markdown, run_drift


async def test_drift_recovers_held_out_quality_after_a_preference_flip():
    report = await run_drift()
    assert report.n == 100

    # F1 vs the *current* truth: learned high, collapses at the flip, re-learns.
    assert 0.85 <= report.f1_before_drift <= 0.87
    assert report.f1_at_drift < report.f1_before_drift - 0.10  # a real collapse
    assert report.f1_after_drift >= report.f1_before_drift      # fully recovered
    assert report.recovered_frac >= 0.90


async def test_stale_pins_are_all_removed_after_the_preference_flip():
    """The un-pinning claim, measured at population scale: every persona whose
    dropped topic had been escalated to a pin has that pin torn down by phase B."""
    report = await run_drift()
    assert len(report.pinned_on_dropped) == 30  # 30 users pinned the now-unwanted topic
    assert report.unpin_frac == 1.0             # …and 100% were un-pinned
    for r in report.pinned_on_dropped:
        assert r.pin_removed


async def test_drift_is_deterministic():
    a, b = await run_drift(), await run_drift()
    assert [r.pin_removed for r in a.results] == [r.pin_removed for r in b.results]
    assert a.f1_after_drift == b.f1_after_drift
    assert "Preference-drift benchmark" in render_markdown(a)
