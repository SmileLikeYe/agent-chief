"""Step 4 acceptance: frozen-time tests produce the expected SceneState for each
of the 7 scenes; confidence 0.5 forces interrupt→digest downgrade."""

from datetime import UTC, datetime

from context.infer import SCENE_POLICY, SceneEngine, downgrade_low_confidence, infer_scene
from context.providers.calendar import CalendarProvider, parse_ics
from context.providers.clock import ClockProvider
from core.policy import parse_policy

NIGHT = datetime(2026, 7, 4, 1, 30, tzinfo=UTC)  # saturday
WEEKDAY_DAY = datetime(2026, 7, 6, 14, 0, tzinfo=UTC)  # monday
SAT_EVENING = datetime(2026, 7, 4, 20, 0, tzinfo=UTC)
SAT_DAY = datetime(2026, 7, 4, 11, 0, tzinfo=UTC)


def test_sleeping():
    s = infer_scene(
        {"quiet_hours": True, "screen_locked": True, "locked_minutes": 45}, now=NIGHT
    )
    assert s.scene == "sleeping" and s.confidence == 0.9


def test_meeting():
    s = infer_scene({"calendar_now": "meeting"}, now=WEEKDAY_DAY)
    assert s.scene == "meeting" and s.confidence == 0.85


def test_deep_work_via_calendar_focus():
    s = infer_scene({"calendar_now": "focus"}, now=WEEKDAY_DAY)
    assert s.scene == "deep_work" and s.confidence == 0.75


def test_deep_work_via_ide():
    s = infer_scene(
        {"foreground_kind": "ide", "foreground_minutes": 30, "active": True}, now=WEEKDAY_DAY
    )
    assert s.scene == "deep_work" and s.confidence == 0.75


def test_commuting():
    s = infer_scene({"calendar_now": "commute"}, now=WEEKDAY_DAY)
    assert s.scene == "commuting" and s.confidence == 0.7


def test_social():
    s = infer_scene({"dnd_mode": "personal"}, now=SAT_EVENING)
    assert s.scene == "social" and s.confidence == 0.5


def test_leisure():
    s = infer_scene({"foreground_kind": "entertainment"}, now=SAT_DAY)
    assert s.scene == "leisure" and s.confidence == 0.6


def test_idle_fallback():
    s = infer_scene({}, now=WEEKDAY_DAY)
    assert s.scene == "idle" and s.confidence == 0.4


# --- low-confidence downgrade (SPEC Principle 2) ---


def test_confidence_below_0_6_downgrades_interrupt_to_digest():
    s = infer_scene({"dnd_mode": "personal"}, now=SAT_EVENING)  # social, conf 0.5
    assert downgrade_low_confidence("interrupt", s) == "digest"


def test_high_confidence_keeps_interrupt():
    s = infer_scene({"calendar_now": "meeting"}, now=WEEKDAY_DAY)  # 0.85
    assert downgrade_low_confidence("interrupt", s) == "interrupt"


def test_non_interrupt_routes_untouched():
    s = infer_scene({}, now=WEEKDAY_DAY)  # idle 0.4
    assert downgrade_low_confidence("digest", s) == "digest"


# --- scene policy table + POLICY.md override ---


def test_default_policy_table():
    assert SCENE_POLICY["sleeping"].interrupt_threshold == 0.95
    assert SCENE_POLICY["meeting"].max_level == "silent"
    assert SCENE_POLICY["idle"].interrupt_threshold == 0.45


def test_policy_md_threshold_override():
    p = parse_policy("## Scene thresholds\n- deep_work = 0.70\n- bogus_scene = 0.5\n")
    assert p.scene_thresholds == {"deep_work": 0.70}


# --- providers ---


def test_clock_provider_signals():
    clock = ClockProvider(quiet_hours="23:00-08:00", now_fn=lambda: NIGHT)
    sig = clock.sample()
    assert sig["quiet_hours"] is True and sig["weekend"] is True


def test_calendar_provider_signals():
    ics = (
        "BEGIN:VEVENT\nDTSTART:20260706T135000Z\nDTEND:20260706T143000Z\n"
        "SUMMARY:Team sync meeting\nEND:VEVENT\n"
        "BEGIN:VEVENT\nDTSTART:20260706T141000Z\nDTEND:20260706T150000Z\n"
        "SUMMARY:Focus block\nEND:VEVENT\n"
    )
    events = parse_ics(ics)
    cal = CalendarProvider(events=events, now_fn=lambda: WEEKDAY_DAY)
    sig = cal.sample()
    assert sig["calendar_now"] == "meeting"
    assert sig["calendar_next_15min"] == "focus"


def test_engine_merges_and_caches():
    calls = {"n": 0}

    class Fake:
        name = "fake"

        def sample(self):
            calls["n"] += 1
            return {"calendar_now": "meeting"}

    t = {"now": WEEKDAY_DAY}
    engine = SceneEngine([Fake()], now_fn=lambda: t["now"])
    assert engine.current().scene == "meeting"
    engine.current()  # within 30s cache window → no resample
    assert calls["n"] == 1


def test_engine_skips_broken_provider():
    class Broken:
        name = "broken"

        def sample(self):
            raise RuntimeError("unavailable on this platform")

    engine = SceneEngine([Broken()], now_fn=lambda: WEEKDAY_DAY)
    assert engine.current().scene == "idle"  # graceful degradation
