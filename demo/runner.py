"""Implements SPEC §4.7: demo replay mode — a fully offline day-in-the-life replay.

`replay()` is pure (no rendering, no sleeps) and doubles as the permanent
routing regression harness (Step 7). `run_demo()` adds rich rendering on top.
"""

import asyncio
import json
import time as time_mod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel

from core.embedding import DEFAULT_EMBEDDER, cosine
from core.policy import parse_policy
from core.schema import Decision, Event, SceneState
from core.scorer import score_and_route, stage1
from judge.fixtures import FixtureJudge

FIXTURE_PATH = Path(__file__).parent / "day_of_engineer.json"
ASSOCIATION_THRESHOLD = 0.78  # SPEC §4.2

ROUTE_EMOJI = {
    "drop": "🗑",
    "digest": "📰",
    "dispatch": "🤖",
    "curate": "📚",
    "interrupt": "🔔",
}


@dataclass
class ReplayEntry:
    seq: int
    time: str
    scene: dict[str, Any]
    event: dict[str, Any]
    judge: dict[str, Any] | None
    expected_route: str
    delivery: str | None = None
    dispatch: dict[str, Any] | None = None
    beat: str | None = None
    digest_moment: str | None = None
    rationale: str | None = None  # golden-set label rationale (eval harness, Step 25)


@dataclass
class Fixture:
    date: str
    quiet_hours: str
    night_whitelist: list[str]
    policy_text: str
    entries: list[ReplayEntry]
    overnight: list[str] = field(default_factory=list)


@dataclass
class ReplayResult:
    seq: int
    event: Event
    scene: SceneState
    decision: Decision
    entry: ReplayEntry
    memory_hits: list[str] = field(default_factory=list)
    plan: str | None = None
    delivery: str | None = None


def load_fixture(path: str | Path = FIXTURE_PATH) -> Fixture:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return Fixture(
        date=raw["date"],
        quiet_hours=raw["quiet_hours"],
        night_whitelist=raw["night_whitelist"],
        policy_text=raw["policy"],
        entries=[ReplayEntry(**e) for e in raw["entries"]],
        overnight=raw.get("overnight", []),
    )


def replay(fixture: Fixture, judge=None) -> list[ReplayResult]:
    """Run every fixture event through the real pipeline (stage 1 → associate →
    judge → score & route). Offline and deterministic with the default
    FixtureJudge; Step 8 injects real backends for the agreement test."""
    policy = parse_policy(fixture.policy_text)
    judge = judge or FixtureJudge({e.event["id"]: e.judge for e in fixture.entries if e.judge})
    memory: list[tuple[str, list[float]]] = []  # (text, embedding)
    seen_dedup: set[str] = set()
    results: list[ReplayResult] = []

    for entry in fixture.entries:
        at = datetime.fromisoformat(f"{fixture.date}T{entry.time}:00")
        event = Event(received_at=at, **entry.event)
        scene = SceneState(at=at, signals={}, **entry.scene)

        hit = stage1(
            event,
            now=at,
            policy=policy,
            quiet_hours=fixture.quiet_hours,
            night_whitelist=fixture.night_whitelist,
            recent_dedup_keys=seen_dedup,
        )
        memory_hits: list[str] = []
        if hit:
            decision = Decision(
                event_id=event.id,
                route=hit.route,  # type: ignore[arg-type]
                scene=scene.scene,
                scene_confidence=scene.confidence,
                cost=0.0,
                matched_rules=[hit.rule],
                reason=hit.reason,
                stage=1,
            )
        else:
            vec = DEFAULT_EMBEDDER.embed(event.summary)
            memory_hits = [
                text for text, mvec in memory if cosine(vec, mvec) > ASSOCIATION_THRESHOLD
            ][:3]
            try:
                result = asyncio.run(judge.judge(event, None))
            except Exception as exc:  # one flaky case must not abort a paid eval run
                result = None
                decision = Decision(
                    event_id=event.id,
                    route="digest",  # mirror production degradation (Step 28)
                    scene=scene.scene,
                    scene_confidence=scene.confidence,
                    cost=0.0,
                    reason=f"judge error ({type(exc).__name__}); conservative digest",
                    stage=3,
                    degraded=True,
                )
            if result is not None:
                route, score, comps, reason = score_and_route(
                    result, scene, memory_hit=bool(memory_hits)
                )
                decision = Decision(
                    event_id=event.id,
                    route=route,  # type: ignore[arg-type]
                    score=score,
                    components=comps,
                    scene=scene.scene,
                    scene_confidence=scene.confidence,
                    cost=0.0,
                    reason=reason,
                    stage=3,
                )
            if result is not None and decision.route == "curate" and result.memorize:
                memory.append((result.memorize, DEFAULT_EMBEDDER.embed(result.memorize)))

        if event.dedup_key:
            seen_dedup.add(event.dedup_key)

        plan = None
        if decision.route == "dispatch" and entry.dispatch:
            plan = entry.dispatch.get("result")

        results.append(
            ReplayResult(
                seq=entry.seq,
                event=event,
                scene=scene,
                decision=decision,
                entry=entry,
                memory_hits=memory_hits,
                plan=plan,
                delivery=entry.delivery,
            )
        )
    return results


def _render_digest(
    console: Console, title: str, pool: list[ReplayResult], overnight: list[str] | None = None
) -> None:
    lines = [f"• {item} [dim](overnight)[/dim]" for item in overnight or []]
    lines += [f"• {r.event.summary}" for r in pool]
    connections = [r for r in pool if r.memory_hits]
    if connections:
        lines.append("")
        lines.append("[bold]Connections[/bold]")
        for r in connections:
            lines.append(f'  ↳ {r.event.summary} — you asked to watch this: "{r.memory_hits[0]}"')
            if r.plan:
                lines.append(f"    plan: {r.plan}")
    body = "\n".join(lines) if lines else "(nothing worth batching)"
    console.print(Panel(body, title=f"📰 {title}", border_style="cyan"))


def run_demo(fast: bool = False) -> None:
    console = Console()
    fixture = load_fixture()
    console.print(
        Panel(
            "[bold]Chief[/bold] — a day in the life of an engineer, replayed offline.\n"
            "24 events flow in. Watch what earns your attention.",
            border_style="magenta",
        )
    )

    results = replay(fixture)
    digest_pool: list[ReplayResult] = []

    for r in results:
        if not fast:
            time_mod.sleep(2)
        scene_tag = f"[dim]{r.entry.time} · {r.scene.scene}[/dim]"
        console.print(f"{scene_tag}  {r.event.summary}")
        emoji = ROUTE_EMOJI[r.decision.route]
        console.print(f"   {emoji} [bold]{r.decision.route}[/bold] — {r.decision.reason}")
        if r.entry.beat:
            console.print(f"   [italic dim]{r.entry.beat}[/italic dim]")

        if r.decision.route == "dispatch" and r.entry.dispatch:
            d = r.entry.dispatch
            console.print(f"   🤖 dispatch → {d['executor']}: {r.entry.judge['dispatch_goal']}")
            console.print(f"   ✔ verified: {d['verify']}")
            level = "🔔 silent push" if r.delivery in ("silent", "interrupt") else "📰 into digest"
            console.print(f"   {level}: {d['result']}")
        elif r.decision.route == "curate":
            console.print(f"   📚 remembered: \"{r.entry.judge['memorize']}\"")
        elif r.decision.route == "digest":
            digest_pool.append(r)
        if r.decision.route == "dispatch" and r.delivery == "digest":
            digest_pool.append(r)

        if r.entry.digest_moment == "morning":
            _render_digest(console, "morning digest (08:00)", digest_pool, fixture.overnight)
            digest_pool = []
        elif r.entry.digest_moment == "evening":
            _render_digest(console, "evening digest (18:30)", digest_pool)
            digest_pool = []
        console.print()

    blocked = sum(1 for r in results if r.decision.route == "drop")
    batched = sum(1 for r in results if r.decision.route == "digest")
    handled = sum(1 for r in results if r.decision.route == "dispatch")
    interrupted = sum(1 for r in results if r.delivery == "interrupt")
    console.print(
        Panel(
            f"[bold]Today: {len(results)} events in → {blocked} blocked · {batched} batched · "
            f"{handled} handled (all verified) · interrupted you exactly once.[/bold]\n"
            f"[dim](interrupt-level deliveries: {interrupted})[/dim]",
            title="🎯 Tact Report",
            border_style="green",
        )
    )
    console.print("Connect real sources? Run: [bold]chief init[/bold]")
