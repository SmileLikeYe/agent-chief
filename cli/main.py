"""Implements SPEC §5: the `chief` CLI surface (typer app with all subcommands)."""

import typer

app = typer.Typer(
    name="chief",
    help="Chief — the chief of staff for your agents and information sources.",
    no_args_is_help=True,
)


def _version(show: bool):
    if show:
        from importlib.metadata import PackageNotFoundError, version

        try:
            typer.echo(f"chief {version('agent-chief')}")
        except PackageNotFoundError:
            typer.echo("chief (source checkout)")
        raise typer.Exit()


@app.callback()
def _main(
    version: bool = typer.Option(
        False, "--version", callback=_version, is_eager=True, help="Show version and exit."
    ),
):
    """Chief — the chief of staff for your agents and information sources."""


@app.command()
def demo(fast: bool = typer.Option(False, "--fast", help="Replay without delays (for tests).")):
    """Offline replay of a day in the life of an engineer (SPEC §4.7)."""
    from demo.runner import run_demo

    run_demo(fast=fast)


@app.command(name="eval")
def eval_cmd(
    backend: str = typer.Option("fixtures", "--backend", help="Judge backend to evaluate."),
    out: str = typer.Option(None, "--out", help="Report directory (default eval/reports/)."),
    compare: tuple[str, str] = typer.Option(
        (None, None), "--compare", help="Diff two prompt versions on the golden set."
    ),
    learning: bool = typer.Option(
        False, "--learning", help="Run the preference-learning (reward-loop) eval."
    ),
    cohort: bool = typer.Option(
        False, "--cohort", help="Run the 100-user cohort preference-learning benchmark."
    ),
    ablation: bool = typer.Option(
        False, "--ablation", help="Ablate each funnel stage on the golden set (accuracy + cost)."
    ),
    calibration: bool = typer.Option(
        False, "--calibration", help="Score discrimination (AUC) + calibration (ECE) on the cohort."
    ),
    redteam: bool = typer.Option(
        False, "--redteam", help="Run the adversarial red-team suite (injection / payloads / §13)."
    ),
):
    """Run REGRESSION (demo 24, must be 100%) + CAPABILITY (golden ~200) evals."""
    from rich.console import Console

    from eval.runner import (
        REPORTS_DIR,
        _writable_dir,
        run_capability,
        run_compare,
        run_regression,
        write_compare_report,
        write_report,
    )

    console = Console()

    if redteam:
        from eval.redteam import render_markdown as render_redteam
        from eval.redteam import run_redteam

        report = run_redteam()
        path = _writable_dir(out or REPORTS_DIR) / "redteam.md"
        path.write_text(render_redteam(report), encoding="utf-8")
        tone = "green" if not report.breaches else "red"
        console.print(
            f"[{tone}]redteam[/{tone}] {report.contained}/{report.total} attacks "
            f"contained across {len(report.categories)} categories → {path}"
        )
        raise typer.Exit(0 if not report.breaches else 1)

    if calibration:
        import asyncio

        from eval.calibration import render_markdown as render_calibration
        from eval.calibration import run_calibration

        if compare[0] or backend != "fixtures":
            console.print(
                "[yellow]note[/yellow]: --calibration ignores --compare/--backend "
                "(it scores the offline cohort's held-out stream)"
            )
        report = asyncio.run(run_calibration())
        path = _writable_dir(out or REPORTS_DIR) / "calibration.md"
        path.write_text(render_calibration(report), encoding="utf-8")
        console.print(
            f"[green]calibration[/green] AUC {report.auc_before:.2f} → "
            f"{report.auc_after:.2f} · ECE {report.ece_raw:.2f} → "
            f"{report.ece_isotonic:.2f} (isotonic) → {path}"
        )
        return

    if ablation:
        import asyncio

        from eval.ablation import render_markdown as render_ablation
        from eval.ablation import run_ablation

        if compare[0] or backend != "fixtures":
            console.print(
                "[yellow]note[/yellow]: --ablation ignores --compare/--backend "
                "(it sweeps the offline fixtures judge to stay deterministic)"
            )
        report = asyncio.run(run_ablation())
        path = _writable_dir(out or REPORTS_DIR) / "ablation.md"
        path.write_text(render_ablation(report), encoding="utf-8")
        console.print(
            f"[green]ablation[/green] full {report.full.agreement:.0%} · "
            f"−stage-1 {report.runs['no_stage1'].agreement:.0%} "
            f"(+{report.stage1_calls_saved} judge calls) · "
            f"−judge {report.runs['no_judge'].agreement:.0%} → {path}"
        )
        return

    if cohort:
        import asyncio

        from eval.cohort import render_markdown as render_cohort
        from eval.cohort import run_cohort

        if compare[0] or backend != "fixtures":
            console.print(
                "[yellow]note[/yellow]: --cohort ignores --compare/--backend "
                "(the reward loop uses the built-in scorer, not an LLM judge)"
            )
        report = asyncio.run(run_cohort())
        path = _writable_dir(out or REPORTS_DIR) / "cohort.md"
        path.write_text(render_cohort(report), encoding="utf-8")
        console.print(
            f"[green]cohort[/green] {report.converged_frac:.0%} of {report.n} users "
            f"converge · held-out interrupt F1 {report.f1_before:.2f} → "
            f"{report.f1_after:.2f} → {path}"
        )
        return

    if learning:
        import asyncio

        from eval.learning import render_markdown as render_learning
        from eval.learning import run_learning

        if compare[0] or backend != "fixtures":
            console.print(
                "[yellow]note[/yellow]: --learning ignores --compare/--backend "
                "(the reward loop uses the built-in scorer, not an LLM judge)"
            )
        report = asyncio.run(run_learning())
        path = _writable_dir(out or REPORTS_DIR) / "learning.md"
        path.write_text(render_learning(report), encoding="utf-8")
        converged = report.rounds_to_converge is not None
        tone = "green" if converged else "red"
        where = (f"converged in {report.rounds_to_converge} rounds"
                 if converged else "did not reach 95%")
        console.print(
            f"[{tone}]learning[/{tone}] agreement {report.baseline:.0%} → "
            f"{report.final:.0%} ({where}) → {path}"
        )
        return

    def build_judge(prompt_version: str | None = None):
        if backend == "fixtures":
            return None  # per-entry judge blocks; prompt-insensitive
        from core.config import load_config
        from judge.factory import make_judge

        llm = load_config().get("llm", {})
        # configured model/base_url/api_key belong to the configured backend
        # only — for a DIFFERENT --backend, start from that provider's
        # defaults; a config with no backend key applies to whatever runs
        cfg = dict(llm) if llm.get("backend") in (None, backend) else {}
        cfg["backend"] = backend
        if prompt_version:
            cfg["prompt_version"] = prompt_version
        return make_judge(cfg)

    out_dir = out or REPORTS_DIR

    if compare[0] and compare[1]:
        version_a, version_b = compare
        report = run_compare(
            build_judge(version_a), build_judge(version_b),
            version_a=version_a, version_b=version_b,
        )
        path = write_compare_report(report, out_dir)
        console.print(
            f"compare {version_a} vs {version_b}: delta {report.delta:+.1%}, "
            f"{len(report.flipped)} flipped → {path}"
        )
        if backend == "fixtures":
            console.print(
                "[yellow]note[/yellow]: the fixtures backend never reads prompts — "
                "run --compare against a real backend for a meaningful diff"
            )
        return

    def warn_if_blind(report):
        broken = sum(1 for r in report.results if r.decision.degraded)
        if broken:
            console.print(
                f"[yellow]warning[/yellow]: {broken}/{report.total} judge calls failed "
                "and were routed conservatively — check credentials/backend before "
                "trusting this agreement number"
            )

    judge = build_judge()
    regression = run_regression(judge)
    warn_if_blind(regression)
    path = write_report(regression, out_dir)
    tone = "green" if regression.agreement == 1.0 else "red"
    console.print(
        f"[{tone}]regression[/{tone}] agreement "
        f"{regression.agreement:.1%} ({regression.agreed}/{regression.total}) → {path}"
    )
    if regression.agreement < 1.0:
        raise typer.Exit(code=1)  # regression must stay 100%; don't pay for capability
    capability = run_capability(judge)
    warn_if_blind(capability)
    path = write_report(capability, out_dir)
    console.print(
        f"[green]capability[/green] agreement "
        f"{capability.agreement:.1%} ({capability.agreed}/{capability.total}) → {path}"
    )


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
            f"cost ${decision.cost:.6f}"
        )
    else:
        console.print("[dim]no trace recorded (pre-v3.1 decision)[/dim]")


@app.command()
def lite(
    event_json: str = typer.Argument(
        None, help="Candidate event as JSON; omit to read from stdin."
    ),
):
    """Judgment only (SPEC v3.1 Step 29): stages 1-3 + routing, no learner,
    no delivery daemon, no persistence. Prints the Decision as JSON.

    Zero-config behavior is conservative: without a configured LLM backend the
    judge is unavailable, so anything stage-1 lets through routes to digest
    with degraded=true — never interrupt, never silently drop.
    """
    import asyncio
    import json
    import sys

    raw = event_json if event_json else sys.stdin.read()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        typer.echo(f"invalid event JSON: {exc}", err=True)
        raise typer.Exit(code=2) from None

    from core.brain import judge_once

    decision = asyncio.run(judge_once(payload))
    typer.echo(decision.model_dump_json())


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
def token():
    """Print the local webhook bearer token for scripts and agents."""
    from core.config import config_path, load_config

    value = load_config().get("ingest", {}).get("webhook_token")
    if not value:
        typer.echo(f"no webhook token at {config_path()} — run: chief init", err=True)
        raise typer.Exit(code=2)
    typer.echo(value)


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
def connect(
    source: str = typer.Argument(..., help="composio | github | rss"),
    secret: str = typer.Option(None, "--secret", help="Composio webhook secret (whsec_…)."),
    url: str = typer.Option(None, "--url", help="RSS feed url."),
):
    """One-click source connection (SPEC v3.2 Step 35)."""
    from cli import connect as c

    if source == "composio":
        if not secret:
            typer.echo("need --secret whsec_… (Composio dashboard → webhook subscription)")
            raise typer.Exit(code=2)
        c.connect_composio(secret)
    elif source == "github":
        c.connect_github()
    elif source == "rss":
        if not url:
            typer.echo("need --url https://…")
            raise typer.Exit(code=2)
        c.connect_rss(url)
    else:
        typer.echo(f"unknown source {source!r} — try: composio, github, rss "
                   "(or POST /v1/events directly, docs/protocol.md)")
        raise typer.Exit(code=2)


@app.command()
def sources():
    """List connectors and their status (SPEC v3.2 Step 35)."""
    from cli.connect import show_sources

    show_sources()


@app.command()
def ui():
    """Serve the local web console at http://127.0.0.1:8787/ui (SPEC v3.2)."""
    import asyncio

    from cli.runtime import run_console

    asyncio.run(run_console())


@app.command()
def status():
    """Show scene / queue / today's stats."""
    import asyncio
    from datetime import UTC, datetime

    from rich.console import Console

    from context.infer import SceneEngine
    from context.providers.clock import ClockProvider
    from core.brain import load_degraded
    from core.config import db_path
    from core.learner import ShadowMode
    from core.state import State

    async def _status():
        async with State.open(db_path()) as state:
            scene = SceneEngine([ClockProvider()]).current()
            counts = await state.route_counts()
            shadow = await ShadowMode(state).active(datetime.now(UTC))
            degraded = await load_degraded(state)
            return scene, counts, shadow, degraded

    scene, counts, shadow, degraded = asyncio.run(_status())
    console = Console()
    console.print(f"scene: [bold]{scene.scene}[/bold] (confidence {scene.confidence:.2f})")
    console.print(f"shadow mode: {'on' if shadow else 'off'}")
    if degraded:
        console.print(
            f"[red]judge: DEGRADED[/red] — rules-only conservative routing "
            f"since {degraded['since']} (last error: {degraded['last_error']})"
        )
    else:
        console.print("judge: healthy")
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
