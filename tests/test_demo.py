"""Step 6 acceptance: `chief demo` runs fully offline end-to-end; visual smoke
test via `--fast`; final report counts match SPEC §4.7."""

from typer.testing import CliRunner

from cli.main import app
from demo.runner import load_fixture, replay

runner = CliRunner()


def test_fixture_has_24_events():
    fixture = load_fixture()
    assert len(fixture.entries) == 24


def test_replay_route_counts_match_spec_finale():
    """SPEC §4.7: 24 in → 14 blocked · 6 batched · 3 handled · interrupted exactly once."""
    results = replay(load_fixture())
    routes = [r.decision.route for r in results]
    assert routes.count("drop") == 14
    assert routes.count("digest") == 6
    assert routes.count("dispatch") == 3
    assert routes.count("curate") == 1
    assert sum(1 for r in results if r.delivery == "interrupt") == 1


def test_association_chain_setup_to_payoff():
    """SPEC §4.7 anchor: #5 curates, #19 hits the memory (proof of thinking)."""
    results = replay(load_fixture())
    by_seq = {r.seq: r for r in results}
    assert by_seq[5].decision.route == "curate"
    assert by_seq[19].memory_hits, "event 19 must recall the memory planted at event 5"


def test_dispatch_events_carry_verified_plans():
    results = replay(load_fixture())
    dispatched = [r for r in results if r.decision.route == "dispatch"]
    assert len(dispatched) == 3
    for r in dispatched:
        assert r.plan, f"dispatch event {r.seq} must arrive with a plan"


def test_cli_demo_fast_smoke():
    result = runner.invoke(app, ["demo", "--fast"])
    assert result.exit_code == 0
    assert "24 events in" in result.output
    assert "14 blocked" in result.output
    assert "interrupted you exactly once" in result.output
    assert "chief init" in result.output
