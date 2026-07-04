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
            f"shadow grading: {grade}",
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
