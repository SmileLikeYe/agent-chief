"""Step 13 acceptance: time-travel test — shadow → 50 graded samples →
graduates → real interrupts enabled; Tact Report renders correct counts."""

from datetime import UTC, datetime, timedelta

from typer.testing import CliRunner

from core.learner import ShadowMode, build_tact_report
from core.schema import Decision
from core.state import State

T0 = datetime(2026, 7, 1, 9, 0, tzinfo=UTC)


def decision(event_id="evt_x", route="interrupt", score=0.87, scene="deep_work"):
    return Decision(
        event_id=event_id,
        route=route,
        score=score,
        scene=scene,
        scene_confidence=0.8,
        cost=0.0,
        reason="t",
        stage=3,
    )


async def test_shadow_active_first_7_days(tmp_path):
    async with State.open(tmp_path / "s.db") as state:
        shadow = ShadowMode(state)
        await shadow.ensure_started(T0)
        assert await shadow.active(T0 + timedelta(days=1))
        assert not await shadow.active(T0 + timedelta(days=8))


async def test_shadow_degrades_interrupt_with_annotation(tmp_path):
    async with State.open(tmp_path / "s.db") as state:
        shadow = ShadowMode(state)
        await shadow.ensure_started(T0)
        route, annotation = await shadow.apply(decision(), now=T0 + timedelta(days=1))
        assert route == "digest"
        assert annotation == "⚡ would have: interrupted you (score 0.87, scene deep_work)"


async def test_shadow_leaves_other_routes_alone(tmp_path):
    async with State.open(tmp_path / "s.db") as state:
        shadow = ShadowMode(state)
        await shadow.ensure_started(T0)
        route, annotation = await shadow.apply(decision(route="digest"), now=T0)
        assert route == "digest" and annotation is None


async def test_50_graded_samples_graduate_early(tmp_path):
    """Time travel: day 2 of shadow, but 50 grades arrive → graduation."""
    async with State.open(tmp_path / "s.db") as state:
        shadow = ShadowMode(state)
        await shadow.ensure_started(T0)
        day2 = T0 + timedelta(days=2)
        assert await shadow.active(day2)
        for i in range(50):
            await state.save_feedback(f"evt_{i}", "shadow_good" if i % 2 else "shadow_bad", day2)
        assert not await shadow.active(day2)  # graduated early
        route, annotation = await shadow.apply(decision(), now=day2)
        assert route == "interrupt" and annotation is None  # real interrupts enabled


async def test_tact_report_counts(tmp_path):
    async with State.open(tmp_path / "s.db") as state:
        now = T0 + timedelta(days=1)
        routes = ["drop"] * 5 + ["digest"] * 3 + ["dispatch"] * 2 + ["interrupt"] * 1
        for i, route in enumerate(routes):
            await state.save_decision(decision(event_id=f"evt_{i}", route=route))
        await state.save_feedback("evt_a", "shadow_good", now)
        await state.save_feedback("evt_b", "shadow_good", now)
        await state.save_feedback("evt_c", "shadow_bad", now)
        report = await build_tact_report(state, days=7, now=now)
        assert report.events_in == 11
        assert report.blocked == 5 and report.batched == 3
        assert report.handled == 2 and report.interrupted == 1
        assert report.graded == 3
        assert report.accuracy == (2, 3)


def test_chief_report_cli(tmp_path, monkeypatch):
    monkeypatch.setenv("CHIEF_HOME", str(tmp_path))
    from cli.main import app

    result = CliRunner().invoke(app, ["report", "--days", "7"])
    assert result.exit_code == 0
    assert "Tact Report" in result.output
