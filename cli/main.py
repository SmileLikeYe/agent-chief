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
    typer.echo("chief digest: not implemented yet")


@app.command()
def status():
    """Show scene / queue / today's stats."""
    typer.echo("chief status: not implemented yet")


@app.command()
def policy(action: str = typer.Argument("show", help="edit | show")):
    """Show or edit POLICY.md."""
    typer.echo("chief policy: not implemented yet")


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
