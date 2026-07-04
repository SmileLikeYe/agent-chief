"""Step 7: the permanent routing regression harness (SPEC §9 Step 7).

Asserts the pipeline route of ALL 24 demo events matches the fixture's
expected table — any scoring/rule/threshold change that shifts a route
breaks this test loudly, one line per event.
"""

import pytest

from demo.runner import load_fixture, replay

FIXTURE = load_fixture()
RESULTS = {r.seq: r for r in replay(FIXTURE)}
EXPECTED = [(e.seq, e.time, e.expected_route) for e in FIXTURE.entries]


@pytest.mark.parametrize(("seq", "at", "expected_route"), EXPECTED)
def test_event_routes_as_expected(seq, at, expected_route):
    result = RESULTS[seq]
    assert result.decision.route == expected_route, (
        f"event #{seq} ({at}) '{result.event.summary}' routed to "
        f"{result.decision.route!r}, fixture expects {expected_route!r} "
        f"(reason: {result.decision.reason})"
    )


def test_full_table_is_complete():
    assert len(EXPECTED) == 24
    assert sorted(RESULTS) == list(range(1, 25))
