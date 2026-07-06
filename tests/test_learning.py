"""Preference-learning harness tests (SPEC v3.2 Step 37): the reward loop
demonstrably trains the policy, deterministically."""

from typer.testing import CliRunner

from eval.learning import (
    INBOX,
    SimUser,
    render_markdown,
    run_learning,
)

# --- the simulated user (reward source) ------------------------------------------


def test_simuser_only_corrects_wrong_routes():
    user = SimUser(wants_interrupt={"prod.incident"})
    # wanted topic not interrupted → nudge up
    assert user.feedback("prod.incident", "digest") == "should_interrupt"
    # unwanted topic interrupted → nudge down
    assert user.feedback("news.spam", "interrupt") == "should_not_interrupt"
    # already correct → silence (no supervision, as in real life)
    assert user.feedback("prod.incident", "interrupt") is None
    assert user.feedback("news.spam", "digest") is None


def test_simuser_agreement_is_interrupt_vs_silence():
    user = SimUser(wants_interrupt={"a"})
    assert user.agrees("a", "interrupt") and not user.agrees("a", "digest")
    assert user.agrees("b", "drop") and not user.agrees("b", "interrupt")


# --- the closed loop ------------------------------------------------------------


async def test_reward_loop_trains_the_policy():
    report = await run_learning(rounds=10)
    assert report.baseline < 0.5  # starts blind and wrong on most topics
    assert report.final >= 0.95  # feedback drives routing to the user's truth
    assert report.improved > 0.4  # a large, real gain
    assert report.rounds_to_converge is not None


async def test_learning_is_monotonic_and_stable():
    report = await run_learning(rounds=12)
    # agreement never regresses round-to-round, and holds at the top
    assert all(a <= b + 1e-9 for a, b in zip(report.curve, report.curve[1:], strict=False))
    assert report.curve[-1] == report.curve[report.rounds_to_converge]


async def test_learning_is_deterministic():
    a = await run_learning(rounds=8)
    b = await run_learning(rounds=8)
    assert a.curve == b.curve  # same seed of events → identical curve


async def test_wanted_weights_rise_unwanted_fall():
    report = await run_learning(rounds=10)
    wanted = [t for t, want, _ in INBOX if want]
    unwanted = [t for t, want, _ in INBOX if not want]
    # default urgency weight is 0.20
    assert all(report.final_weights[t]["urgency"] > 0.20 for t in wanted)
    assert all(report.final_weights[t]["urgency"] < 0.20 for t in unwanted)


async def test_no_feedback_means_no_learning():
    # a user who agrees with everything supplies no signal → weights untouched
    from core.state import State

    class ContentUser(SimUser):
        def feedback(self, topic, route):
            return None

    import eval.learning as L

    original = L.SimUser
    L.SimUser = ContentUser
    try:
        async with State.open(":memory:") as st:
            report = await run_learning(rounds=5, state=st)
            # every topic still at default (nothing was ever stored)
            assert all(w["urgency"] == 0.20 for w in report.final_weights.values())
    finally:
        L.SimUser = original


# --- report + CLI ------------------------------------------------------------------


async def test_markdown_report_shows_curve_and_weights():
    md = render_markdown(await run_learning(rounds=6))
    assert "Routing agreement" in md
    assert "Learning curve" in md
    assert "converged in" in md
    assert "prod.incident" in md  # per-topic learned weights listed


def test_cli_eval_learning_writes_report(tmp_path):
    from cli.main import app

    result = CliRunner().invoke(app, ["eval", "--learning", "--out", str(tmp_path)])
    assert result.exit_code == 0, result.output
    report = tmp_path / "learning.md"
    assert report.exists()
    assert "reward loop" in report.read_text(encoding="utf-8").lower()
