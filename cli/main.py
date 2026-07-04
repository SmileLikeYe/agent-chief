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
def init():
    """Interactive onboarding wizard (SPEC §4.8)."""
    typer.echo("chief init: not implemented yet")


@app.command()
def run():
    """Resident process: event loop + scheduled jobs (SPEC §2)."""
    typer.echo("chief run: not implemented yet")


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
    typer.echo("chief report: not implemented yet")


@app.command(name="install-service")
def install_service():
    """Emit launchd/systemd service units."""
    typer.echo("chief install-service: not implemented yet")


if __name__ == "__main__":
    app()
