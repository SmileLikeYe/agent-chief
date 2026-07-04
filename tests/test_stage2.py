"""Step 9 acceptance: seeded-set tests for both stage-2 shortcut paths and
pass-through; triage-merge test for near-duplicate events."""

from datetime import UTC, datetime, timedelta

from core.embedding import HashEmbedder, make_embedder
from core.schema import Event
from core.scorer import SimilarityClassifier, find_mergeable, merge_events

NOW = datetime(2026, 7, 6, 10, 0, tzinfo=UTC)


def ev(id="evt_1", topic="dev.ci", summary="CI failed on main: test_auth_flow broken", **kw):
    kw.setdefault("received_at", NOW)
    return Event(id=id, source="t", topic=topic, summary=summary, **kw)


# --- stage-2 shortcuts (SPEC §4.4) ---


def seeded() -> SimilarityClassifier:
    clf = SimilarityClassifier(embedder=HashEmbedder())
    clf.add_dismissed("LinkedIn: 3 new connection requests waiting for you")
    clf.add_dismissed("X: 5 new followers this week on your account")
    clf.add_engaged("CI failed on main: test_auth_flow broken by PR", route="dispatch")
    clf.add_engaged("Flight CA1857 delayed 2.5h tonight", route="interrupt")
    return clf


def test_dismissed_similar_with_no_engaged_record_drops():
    verdict = seeded().classify("LinkedIn: 3 new connection requests waiting for you today")
    assert verdict.action == "drop"
    assert verdict.similarity > 0.88


def test_engaged_similar_skips_judge_and_routes_by_history():
    verdict = seeded().classify("CI failed on main: test_auth_flow broken by PR again")
    assert verdict.action == "route"
    assert verdict.route == "dispatch"


def test_unfamiliar_event_passes_through_to_stage3():
    verdict = seeded().classify("Volcano eruption disrupts European air traffic")
    assert verdict.action == "pass"


def test_engaged_wins_over_dismissed_when_both_similar():
    clf = SimilarityClassifier(embedder=HashEmbedder())
    text = "Weekly digest of dependency updates for repo agent-chief"
    clf.add_dismissed(text)
    clf.add_engaged(text, route="digest")
    verdict = clf.classify(text)
    assert verdict.action == "route"  # engaged record exists → never the drop shortcut


def test_empty_sets_pass_through():
    clf = SimilarityClassifier(embedder=HashEmbedder())
    assert clf.classify("anything at all").action == "pass"


# --- triage merge (SPEC §4.2 step 1) ---


def test_near_duplicates_merge():
    a = ev(id="evt_a", summary="CI failed on main: test_auth_flow broken by PR #482",
           evidence=["https://ci/run/1"])
    b = ev(id="evt_b", summary="CI failed on main: test_auth_flow broken by PR #482 (retry)",
           evidence=["https://ci/run/2"], received_at=NOW + timedelta(minutes=5))
    assert find_mergeable(b, [a], embedder=HashEmbedder()) is a
    merged = merge_events(a, b)
    assert merged.id == "evt_a"
    assert set(merged.evidence) == {"https://ci/run/1", "https://ci/run/2"}
    assert "retry" in merged.summary and len(merged.summary) <= 200


def test_different_topic_never_merges():
    a = ev(id="evt_a", topic="dev.ci")
    b = ev(id="evt_b", topic="dev.build", received_at=NOW + timedelta(minutes=5))
    assert find_mergeable(b, [a], embedder=HashEmbedder()) is None


def test_outside_10min_window_never_merges():
    a = ev(id="evt_a")
    b = ev(id="evt_b", received_at=NOW + timedelta(minutes=11))
    assert find_mergeable(b, [a], embedder=HashEmbedder()) is None


def test_dissimilar_summaries_never_merge():
    a = ev(id="evt_a", summary="CI failed on main: test_auth_flow broken")
    b = ev(id="evt_b", summary="Marketing newsletter about cloud credits promo deals",
           received_at=NOW + timedelta(minutes=5))
    assert find_mergeable(b, [a], embedder=HashEmbedder()) is None


# --- embedder wiring ---


def test_make_embedder_hash_default():
    assert isinstance(make_embedder({}), HashEmbedder)
    assert isinstance(make_embedder({"embedding_model": "hash"}), HashEmbedder)


def test_make_embedder_sentence_transformers_falls_back_when_missing():
    emb = make_embedder({"embedding_model": "bge-small-en-v1.5"})
    vec = emb.embed("hello world")
    assert isinstance(vec, list) and len(vec) > 0
