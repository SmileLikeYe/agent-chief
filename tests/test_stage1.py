"""Step 3 acceptance: table-driven tests covering every stage-1 hard rule,
incl. night-whitelist passthrough and unparseable POLICY lines."""

from datetime import UTC, datetime

import pytest

from core.policy import Policy, parse_policy
from core.schema import Event
from core.scorer import stage1

NIGHT = datetime(2026, 7, 4, 23, 30, tzinfo=UTC)
DAY = datetime(2026, 7, 4, 14, 0, tzinfo=UTC)

POLICY_TEXT = """# POLICY

## Muted topics
- marketing.newsletter

## Rules
- production_incident.* -> interrupt
- fun.cats -> digest
- this line is not parseable at all
- nonsense.topic -> teleport

## Learned
- Prefers silence during deep work (learned 2026-07-01, source: stats)
"""


def make_event(topic="dev.ci", summary="CI failed on main", dedup_key=None, **kw) -> Event:
    return Event(
        id="evt_test",
        source="test",
        topic=topic,
        summary=summary,
        dedup_key=dedup_key,
        received_at=kw.pop("received_at", DAY),
        **kw,
    )


@pytest.fixture
def policy() -> Policy:
    return parse_policy(POLICY_TEXT)


def run(event, *, now=DAY, policy=None, recent=frozenset()):
    return stage1(
        event,
        now=now,
        policy=policy or parse_policy(""),
        quiet_hours="23:00-08:00",
        night_whitelist=["family", "production_incident"],
        recent_dedup_keys=recent,
    )


# --- table-driven rule coverage ---


def test_quiet_hours_routes_to_digest():
    hit = run(make_event(), now=NIGHT)
    assert hit.route == "digest"
    assert hit.rule == "quiet_hours"


def test_night_whitelist_topic_passes_through():
    ev = make_event(topic="production_incident.db_down", summary="DB is down")
    hit = run(ev, now=NIGHT)
    # whitelisted topics are NOT silenced by quiet hours; no stage-1 route forced
    assert hit is None or hit.rule != "quiet_hours"


def test_muted_topic_drops(policy):
    ev = make_event(topic="marketing.newsletter", summary="Our July newsletter is here")
    hit = run(ev, policy=policy)
    assert hit.route == "drop"
    assert hit.rule == "muted_topic"


def test_dedup_drops():
    ev = make_event(dedup_key="k1")
    hit = run(ev, recent=frozenset({"k1"}))
    assert hit.route == "drop"
    assert hit.rule == "dedup"


def test_fresh_dedup_key_passes():
    ev = make_event(dedup_key="k2")
    assert run(ev, recent=frozenset({"k1"})) is None


@pytest.mark.parametrize(
    "summary",
    [
        "All clear, nothing to report",
        "Heartbeat: everything all normal",
        "Nightly check complete, all good",
    ],
)
def test_zero_information_drops(summary):
    hit = run(make_event(topic="ops.heartbeat", summary=summary))
    assert hit.route == "drop"
    assert hit.rule == "zero_information"


def test_regex_match_alone_is_not_zero_information():
    # matches the regex ("all clear") but is semantically substantive → must NOT drop
    ev = make_event(
        topic="ops.security",
        summary="Security audit found the breach; firewall now reports all clear after patch",
    )
    hit = run(ev)
    assert hit is None or hit.rule != "zero_information"


def test_policy_rule_routes_directly(policy):
    ev = make_event(topic="production_incident.api", summary="API 500s spiking")
    hit = run(ev, policy=policy)
    assert hit.route == "interrupt"
    assert hit.rule.startswith("policy:")


def test_policy_glob_rule(policy):
    ev = make_event(topic="fun.cats", summary="A cat did a thing")
    hit = run(ev, policy=policy)
    assert hit.route == "digest"


def test_no_rule_hit_returns_none():
    assert run(make_event()) is None


# --- POLICY.md parser ---


def test_parse_policy_collects_muted_and_rules(policy):
    assert "marketing.newsletter" in policy.muted_topics
    assert any(
        r.pattern == "production_incident.*" and r.route == "interrupt" for r in policy.rules
    )


def test_unparseable_lines_ignored_with_warning(caplog):
    with caplog.at_level("WARNING"):
        p = parse_policy(POLICY_TEXT)
    # bad line and invalid route are skipped, valid rules survive
    assert len(p.rules) == 2
    assert "not parseable" in caplog.text or "teleport" in caplog.text


def test_empty_policy_parses():
    p = parse_policy("")
    assert p.muted_topics == set() and p.rules == []
