"""Deterministic generator for eval/golden.jsonl (~200 labeled events).

Labels are RULE-FIRST: each scenario template states the route it must produce
(and why), and generation fails loudly if the real pipeline disagrees — so the
committed labels are verified against the exact production code paths. The
fixture backend therefore scores ~100% (the sanity ceiling); real backends
diverge and that divergence is the capability number.

Run: `uv run python -m eval.generate_golden` (rewrites eval/golden.jsonl).
"""

import json
from pathlib import Path

DATE = "2026-07-06"
QUIET = "23:00-08:00"
WHITELIST = ["family", "production_incident"]
POLICY = (
    "## Muted topics\n"
    "- crypto.airdrop\n"
    "- marketing.*\n"
    "- social.likes\n"
    "\n"
    "## Rules\n"
    "- dev.ci.nightly -> digest\n"
    "- news.roundup -> digest\n"
)

# scene name -> (interrupt threshold, a daytime HH:MM base)
SCENES = {
    "idle": (0.45, "09:{m:02d}"),
    "leisure": (0.50, "20:{m:02d}"),
    "commuting": (0.60, "08:{m:02d}"),
    "social": (0.70, "19:{m:02d}"),
    "deep_work": (0.85, "10:{m:02d}"),
    "meeting": (0.90, "14:{m:02d}"),
}
DAY_SCENES = list(SCENES)

TOPICS = [
    "dev.ci", "dev.review", "infra.disk", "infra.alerts", "finance.stocks",
    "news.ai", "travel.flight_change", "home.iot", "health.reminder",
    "ops.backup", "sec.scan", "legal.contract",
]

ZERO_INFO = [
    "All clear, nothing to report.",
    "Heartbeat: all clear, nothing to report.",
    "Heartbeat check complete, all good.",
    "Nothing new to report, all systems normal.",
    "Nightly check complete, everything all good.",
    "Nightly backup check complete, all good.",
    "Evening check: all good, nothing new.",
    "Everything is all normal.",
    "Heartbeat: everything all normal.",
    "Evening check: all good, nothing new to report.",
]

cases: list[dict] = []


def judge(score: float, *, dispatchable=False, goal=None, memorize=None, reason="") -> dict:
    return {
        "urgency": score, "relevance": score, "actionability": score,
        "novelty": score, "confidence": score,
        "dispatchable": dispatchable, "dispatch_goal": goal,
        "memorize": memorize, "reason": reason or f"synthetic judge, target score {score}",
    }


def add(time, scene, conf, event, jr, route, rationale):
    n = len(cases) + 1
    event = {"id": f"evt_gold_{n:03d}", **event}
    event.setdefault("dedup_key", f"gold-{n:03d}")
    cases.append({
        "type": "case", "seq": n, "time": time,
        "scene": {"scene": scene, "confidence": conf},
        "event": event, "judge": jr, "expected_route": route, "rationale": rationale,
    })


def day(i, scene):  # a distinct daytime HH:MM for case i in a given scene
    return SCENES[scene][1].format(m=i % 60)


# 1 · zero-information drops (20): day and night, stage-1 kills them all
for i in range(20):
    phrase = ZERO_INFO[i % len(ZERO_INFO)]
    night = i % 4 == 0
    add(
        f"02:{i:02d}" if night else day(i, "idle"),
        "sleeping" if night else "idle", 0.9 if night else 0.7,
        {"source": f"heartbeat-{i}", "topic": "ops.heartbeat", "summary": phrase},
        None, "drop", "zero-information report: regex + canned-set similarity both fire",
    )

# 2 · muted-topic drops (12)
for i, topic in enumerate(
    ["crypto.airdrop", "marketing.newsletter", "marketing.promo", "social.likes"] * 3
):
    add(
        day(i, "leisure"), "leisure", 0.8,
        {"source": "feed", "topic": topic, "summary": f"Promotion blast #{i}: act now, limited"},
        None, "drop", f"topic {topic} is muted in POLICY.md",
    )

# 3 · dedup drops (8): four pairs — first instance digests, repeat drops
for i in range(4):
    key = f"dup-{i}"
    payload = {
        "source": "ci", "topic": "dev.ci",
        "summary": f"Flaky test quarantine report for suite {i}", "dedup_key": key,
    }
    add(day(2 * i, "idle"), "idle", 0.7, dict(payload), judge(0.42),
        "digest", "first occurrence: mid score, batch it")
    add(day(2 * i + 1, "idle"), "idle", 0.7, dict(payload), None,
        "drop", "same dedup_key within 24h: duplicate")

# 4 · quiet-hours conversions (15): night, non-whitelist → digest by rule
for i in range(15):
    topic = TOPICS[i % len(TOPICS)]
    add(
        f"23:{(i * 3) % 60:02d}", "sleeping", 0.9,
        {"source": "watcher", "topic": topic,
         "summary": f"{topic} update #{i}: notable but it is the middle of the night"},
        None, "digest", "quiet hours: non-whitelisted topics defer to morning digest",
    )

# 5 · night whitelist (6): 3 ring-worthy interrupts, 3 below the 0.95 bar
for i in range(3):
    add(
        f"03:{10 + i:02d}", "sleeping", 0.9,
        {"source": "pager", "topic": "production_incident",
         "summary": f"Sev-1 #{i}: primary database down, error rate 100%"},
        judge(0.97, reason="sev-1 outage"), "interrupt",
        "whitelisted at night and score clears the sleeping threshold 0.95",
    )
for i in range(3):
    add(
        f"04:{10 + i:02d}", "sleeping", 0.9,
        {"source": "family-bot", "topic": "family",
         "summary": f"Family note #{i}: package delivered to the front door"},
        judge(0.55), "digest",
        "whitelisted topic passes quiet hours but score is below the sleeping bar",
    )

# 6 · POLICY rule routes (8)
for i in range(4):
    add(day(i, "deep_work"), "deep_work", 0.8,
        {"source": "ci", "topic": "dev.ci.nightly",
         "summary": f"Nightly build #{i}: 2 new warnings, no failures"},
        None, "digest", "user rule: dev.ci.nightly -> digest")
for i in range(4):
    add(day(i + 4, "leisure"), "leisure", 0.8,
        {"source": "rss", "topic": "news.roundup",
         "summary": f"Weekly roundup #{i}: ecosystem news and releases"},
        None, "digest", "user rule: news.roundup -> digest")

# 7 · judge-driven digests (45): scores in [0.40, threshold)
for i in range(45):
    scene = DAY_SCENES[i % len(DAY_SCENES)]
    thr = SCENES[scene][0]
    score = round(min(0.40 + (i % 7) * 0.03, thr - 0.05), 2)
    topic = TOPICS[i % len(TOPICS)]
    add(day(i, scene), scene, 0.75,
        {"source": "agent", "topic": topic,
         "summary": f"{topic}: development #{i} worth a look later, not now"},
        judge(score), "digest",
        f"score {score} sits in the digest band for {scene} (threshold {thr})")

# 8 · judge-driven drops (25): scores < 0.40, nothing to remember
for i in range(25):
    scene = DAY_SCENES[i % len(DAY_SCENES)]
    topic = TOPICS[(i + 3) % len(TOPICS)]
    score = round(0.15 + (i % 5) * 0.05, 2)
    add(day(i + 5, scene), scene, 0.75,
        {"source": "feed", "topic": topic,
         "summary": f"{topic}: minor chatter #{i}, low signal"},
        judge(score), "drop", f"score {score} under the 0.40 digest floor, no memorize")

# 9 · curates (15): low score but carries a fact worth remembering
for i in range(15):
    scene = DAY_SCENES[i % len(DAY_SCENES)]
    topic = TOPICS[(i + 6) % len(TOPICS)]
    add(day(i + 11, scene), scene, 0.75,
        {"source": "agent", "topic": topic,
         "summary": f"{topic}: background fact #{i} for future reference"},
        judge(0.3, memorize=f"watch: {topic} item {i} may matter next quarter"),
        "curate", "score under the floor but memorize is set: keep for later")

# 10 · interrupts (20): clear the scene threshold with confident scenes
for i in range(20):
    scene = DAY_SCENES[i % len(DAY_SCENES)]
    thr = SCENES[scene][0]
    score = round(min(thr + 0.07, 0.99), 2)
    topic = TOPICS[i % len(TOPICS)]
    add(day(i + 17, scene), scene, 0.85,
        {"source": "monitor", "topic": topic, "claimed_urgency": "high",
         "summary": f"{topic}: incident #{i} needs a human decision right now"},
        judge(score, reason="time-critical"), "interrupt",
        f"score {score} clears the {scene} threshold {thr} with confident scene")

# 11 · dispatches (12): dispatchable prep work in interrupt/digest band
for i in range(12):
    scene = DAY_SCENES[i % len(DAY_SCENES)]
    thr = SCENES[scene][0]
    score = round(thr - 0.05 if i % 2 else min(thr + 0.07, 0.99), 2)
    add(day(i + 37, scene), scene, 0.85,
        {"source": "ci", "topic": "dev.ci",
         "summary": f"CI failure #{i}: fixable test breakage on main"},
        judge(score, dispatchable=True, goal=f"fix failing test #{i} on main"),
        "dispatch", "dispatchable with actionable goal: prep work runs first")

# 12 · low-confidence downgrades (10): would interrupt, scene too uncertain
for i in range(10):
    scene = DAY_SCENES[i % len(DAY_SCENES)]
    thr = SCENES[scene][0]
    score = round(min(thr + 0.07, 0.99), 2)
    topic = TOPICS[(i + 2) % len(TOPICS)]
    add(day(i + 49, scene), scene, 0.5,
        {"source": "monitor", "topic": topic,
         "summary": f"{topic}: urgent-looking alert #{i} amid ambiguous context"},
        judge(score), "digest",
        f"score {score} beats the bar but scene confidence 0.5 < 0.6 downgrades")

# 13 · association chain (4): curate a watch-intent, then a related event digests
add("11:00", "idle", 0.8,
    {"source": "agent", "topic": "news.ai",
     "summary": "Acme Labs teased their next SDK release for later this year"},
    judge(0.3, memorize="Acme Labs teased their next SDK release"),
    "curate", "watch-intent planted for future association")
add("11:05", "idle", 0.8,
    {"source": "agent", "topic": "finance.stocks",
     "summary": "Broker note: chip supplier margins to compress next half"},
    judge(0.3, memorize="chip supplier margins to compress next half"),
    "curate", "second watch-intent planted")
add("16:00", "idle", 0.8,
    {"source": "rss", "topic": "news.ai",
     "summary": "Acme Labs teased their next SDK release date: September 14"},
    judge(0.42), "digest",
    "memory hit boosts relevance; still lands in the digest band")
add("16:05", "idle", 0.8,
    {"source": "rss", "topic": "finance.stocks",
     "summary": "Broker note: chip supplier margins to compress next half, cut to hold"},
    judge(0.42), "digest",
    "second association hit; digest with connection annotation")


def main() -> None:
    from demo.runner import replay
    from eval.runner import GOLDEN_PATH, load_golden

    meta = {"type": "meta", "date": DATE, "quiet_hours": QUIET,
            "night_whitelist": WHITELIST, "policy": POLICY}
    lines = [json.dumps(meta, ensure_ascii=False)]
    lines += [json.dumps(c, ensure_ascii=False) for c in cases]
    Path(GOLDEN_PATH).write_text("\n".join(lines) + "\n", encoding="utf-8")

    # verify every label against the real pipeline before accepting the file
    results = replay(load_golden())
    bad = [r for r in results if r.decision.route != r.entry.expected_route]
    for r in bad:
        print(f"LABEL MISMATCH {r.event.id}: expected {r.entry.expected_route}, "
              f"pipeline says {r.decision.route} ({r.decision.reason})")
    if bad:
        raise SystemExit(f"{len(bad)} label mismatches — fix the generator")
    print(f"wrote {len(cases)} verified cases to {GOLDEN_PATH}")


if __name__ == "__main__":
    main()
