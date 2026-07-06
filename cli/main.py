"""Implements SPEC §5: the `chief` CLI surface (typer app with all subcommands)."""

import typer

app = typer.Typer(
    name="chief",
    help="Chief — the chief of staff for your agents and information sources.",
    no_args_is_help=True,
)


@app.command()
def demo(fast: bool = typer.Option(False, "--fast", help="Replay without delays (for tests).")):
    """Offline replay of a day in the life of an engineer (SPEC §4.7)."""
    from demo.runner import run_demo

    run_demo(fast=fast)


@app.command(name="eval")
def eval_cmd(
    backend: str = typer.Option("fixtures", "--backend", help="Judge backend to evaluate."),
    out: str = typer.Option(None, "--out", help="Report directory (default eval/reports/)."),
):
    """Run REGRESSION (demo 24, must be 100%) + CAPABILITY (golden ~200) evals."""
    from rich.console import Console

    from eval.runner import REPORTS_DIR, run_capability, run_regression, write_report

    console = Console()
    judge = None
    if backend != "fixtures":
        from core.config import load_config
        from judge.factory import make_judge

        judge = make_judge({**load_config().get("llm", {}), "backend": backend})

    out_dir = out or REPORTS_DIR
    for report in (run_regression(judge), run_capability(judge)):
        path = write_report(report, out_dir)
        tone = "green" if report.kind == "capability" or report.agreement == 1.0 else "red"
        console.print(
            f"[{tone}]{report.kind}[/{tone}] agreement "
            f"{report.agreement:.1%} ({report.agreed}/{report.total}) → {path}"
        )
        if report.kind == "regression" and report.agreement < 1.0:
            raise typer.Exit(code=1)  # regression must stay 100%


@app.command()
def trace(event_id: str = typer.Argument(..., help="Event id, e.g. evt_20260706_1040_ab12.")):
    """Replay the full decision chain for one event (SPEC v3.1 Step 26)."""
    import asyncio

    from rich.console import Console
    from rich.table import Table

    from core.config import db_path
    from core.state import State

    async def _load():
        async with State.open(db_path()) as state:
            return await state.load_event(event_id), await state.load_decision(event_id)

    event, decision = asyncio.run(_load())
    if not decision:
        typer.echo(f"no decision recorded for {event_id}")
        raise typer.Exit(code=1)

    console = Console()
    if event:
        console.print(f"[bold]{event.summary}[/bold]  [dim]{event.topic} · {event.source}[/dim]")
    console.print(
        f"route [bold]{decision.route}[/bold] at stage {decision.stage} "
        f"in scene {decision.scene} (confidence {decision.scene_confidence:.2f})"
    )
    if decision.matched_rules:
        console.print(f"rules matched: {', '.join(decision.matched_rules)}")
    if decision.score is not None:
        comps = " ".join(f"{k}={v:.2f}" for k, v in (decision.components or {}).items())
        console.print(f"score {decision.score:.2f}  [dim]{comps}[/dim]")
    console.print(f"reason: {decision.reason}")

    t = decision.trace
    if t:
        table = Table(title="stages")
        table.add_column("stage")
        table.add_column("ms", justify="right")
        table.add_column("note")
        for s in t.stages:
            table.add_row(s.stage, f"{s.ms:.1f}", s.note)
        console.print(table)
        console.print(
            f"tokens: {t.tokens_in} in ({t.cached_tokens} cached) / {t.tokens_out} out · "
            f"backend {t.backend or '—'} · prompt {t.prompt_version or '—'} · "
            f"cost ${t.usd_cost:.6f}"
        )
    else:
        console.print("[dim]no trace recorded (pre-v3.1 decision)[/dim] $0")


@app.command()
def init(
    defaults: bool = typer.Option(
        False, "--defaults", help="Accept all defaults, ask nothing."
    ),
):
    """Interactive onboarding wizard (SPEC §4.8)."""
    from cli.init import run_wizard

    run_wizard(defaults_only=defaults)


@app.command()
def run(
    once: bool = typer.Option(False, "--once", hidden=True, help="Assemble, verify, exit."),
):
    """Resident process: event loop + scheduled jobs (SPEC §2)."""
    import asyncio

    from cli.runtime import run_resident

    asyncio.run(run_resident(once=once))


@app.command()
def digest(now: bool = typer.Option(False, "--now", help="Send the digest immediately.")):
    """Send or schedule the digest."""
    import asyncio
    from datetime import UTC, datetime, timedelta

    from core.config import db_path
    from core.digest import build_digest, render_digest
    from core.state import State
    from memory.store import MemoryStore

    async def _digest():
        async with State.open(db_path()) as state:
            at = datetime.now(UTC)
            d = await build_digest(
                state, MemoryStore(state), since=at - timedelta(hours=24), now=at
            )
            return render_digest(d)

    if not now:
        typer.echo("digest is sent at the configured times by `chief run`; use --now to force")
        return
    typer.echo(asyncio.run(_digest()))


@app.command()
def status():
    """Show scene / queue / today's stats."""
    import asyncio
    from datetime import UTC, datetime

    from rich.console import Console

    from context.infer import SceneEngine
    from context.providers.clock import ClockProvider
    from core.config import db_path
    from core.learner import ShadowMode
    from core.state import State

    async def _status():
        async with State.open(db_path()) as state:
            scene = SceneEngine([ClockProvider()]).current()
            counts = await state.route_counts()
            shadow = await ShadowMode(state).active(datetime.now(UTC))
            return scene, counts, shadow

    scene, counts, shadow = asyncio.run(_status())
    console = Console()
    console.print(f"scene: [bold]{scene.scene}[/bold] (confidence {scene.confidence:.2f})")
    console.print(f"shadow mode: {'on' if shadow else 'off'}")
    console.print(
        "decisions: "
        + " · ".join(f"{route} {n}" for route, n in sorted(counts.items()))
        if counts
        else "decisions: none yet"
    )


@app.command()
def policy(action: str = typer.Argument("show", help="edit | show")):
    """Show or edit POLICY.md."""
    import os
    import subprocess

    from core.config import policy_path

    path = policy_path()
    if action == "edit":
        editor = os.environ.get("EDITOR", "nano")
        subprocess.run([editor, str(path)], check=False)
        return
    if path.exists():
        typer.echo(path.read_text(encoding="utf-8"))
    else:
        typer.echo(f"no POLICY.md yet at {path} — run: chief init")


@app.command()
def report(days: int = typer.Option(7, "--days", help="Reporting window in days.")):
    """Render the Tact Report."""
    import asyncio
    from datetime import UTC, datetime

    from rich.console import Console
    from rich.panel import Panel

    from core.config import db_path
    from core.learner import build_tact_report
    from core.state import State

    async def _build():
        async with State.open(db_path()) as state:
            return await build_tact_report(state, days=days, now=datetime.now(UTC))

    r = asyncio.run(_build())
    good, total = r.accuracy
    grade = f"{good}/{total} graded ✓" if total else "no grades yet"
    Console().print(
        Panel(
            f"{r.events_in} events in → {r.blocked} blocked · {r.batched} batched · "
            f"{r.handled} handled · {r.interrupted} interrupts\n"
            f"shadow grading: {grade}\n"
            f"cost: {r.llm_share:.0%} of events reached the LLM · "
            f"cache hit rate {r.cache_hit_rate:.0%} · "
            f"judgment cost ${r.judgment_cost:.4f}",
            title=f"🎯 Tact Report (last {r.days} days)",
            border_style="green",
        )
    )


@app.command(name="install-service")
def install_service():
    """Emit launchd/systemd service units."""
    from cli.init import install_service as do_install

    do_install()


if __name__ == "__main__":
    app()
