"""Eval runner: routing agreement, bucketed by route / topic / scene.

Golden cases reuse the demo replay pipeline (`demo/runner.py::replay`) so the
eval exercises exactly the code paths production uses: stage-1 rules →
association → judge → score_and_route. The judge under test is swappable;
everything else is held constant, so agreement deltas isolate judge quality.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from demo.runner import FIXTURE_PATH, Fixture, ReplayEntry, ReplayResult, load_fixture, replay

GOLDEN_PATH = Path(__file__).parent / "golden.jsonl"
REPORTS_DIR = Path(__file__).parent / "reports"


def load_golden(path: str | Path = GOLDEN_PATH) -> Fixture:
    """golden.jsonl: line 1 is a meta record; each further line is one case."""
    import json

    lines = Path(path).read_text(encoding="utf-8").splitlines()
    meta = json.loads(lines[0])
    entries = []
    for line in lines[1:]:
        case = json.loads(line)
        case.pop("type")
        entries.append(ReplayEntry(**case))
    return Fixture(
        date=meta["date"],
        quiet_hours=meta["quiet_hours"],
        night_whitelist=meta["night_whitelist"],
        policy_text=meta["policy"],
        entries=entries,
    )


@dataclass
class EvalReport:
    kind: str  # "regression" | "capability"
    backend: str
    results: list[ReplayResult]

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def agreed(self) -> int:
        return sum(1 for r in self.results if r.decision.route == r.entry.expected_route)

    @property
    def agreement(self) -> float:
        return self.agreed / self.total if self.total else 0.0

    @property
    def mismatches(self) -> list[ReplayResult]:
        return [r for r in self.results if r.decision.route != r.entry.expected_route]

    def buckets(self, by: str) -> list[tuple[str, int, int]]:
        """(bucket name, agreed, total) rows; by ∈ route|topic|scene."""
        keys = {
            "route": lambda r: r.entry.expected_route,
            "topic": lambda r: r.event.topic.split(".")[0],
            "scene": lambda r: r.scene.scene,
        }[by]
        groups: dict[str, list[ReplayResult]] = {}
        for r in self.results:
            groups.setdefault(keys(r), []).append(r)
        return [
            (name, sum(1 for r in rs if r.decision.route == r.entry.expected_route), len(rs))
            for name, rs in sorted(groups.items())
        ]


def run_regression(judge=None) -> EvalReport:
    """The demo 24 — must stay 100% (CI gate lives in tests/test_eval.py)."""
    fixture = load_fixture(FIXTURE_PATH)
    results = replay(fixture, judge=judge)
    return EvalReport(kind="regression", backend=_name(judge), results=results)


def run_capability(judge=None, path: str | Path = GOLDEN_PATH) -> EvalReport:
    """The golden ~200 — improvable; report the number, never gate on it."""
    fixture = load_golden(path)
    results = replay(fixture, judge=judge)
    return EvalReport(kind="capability", backend=_name(judge), results=results)


def _name(judge) -> str:
    return getattr(judge, "name", "fixtures") if judge else "fixtures"


def render_markdown(report: EvalReport, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    lines = [
        f"# {report.kind.title()} eval — backend `{report.backend}`",
        "",
        f"_{now:%Y-%m-%d %H:%M} UTC_",
        "",
        f"**Routing agreement: {report.agreement:.1%}** "
        f"({report.agreed}/{report.total})",
        "",
    ]
    for by, title in (("route", "By route"), ("topic", "By topic"), ("scene", "By scene")):
        lines += [f"## {title}", "", "| bucket | agreement | n |", "|---|---|---|"]
        for name, agreed, total in report.buckets(by):
            lines.append(f"| {name} | {agreed / total:.1%} | {agreed}/{total} |")
        lines.append("")
    lines += ["## Mismatches", ""]
    if not report.mismatches:
        lines.append("_none_")
    for r in report.mismatches:
        lines.append(
            f"- `{r.event.id}` [{r.event.topic} · {r.scene.scene}] "
            f"expected **{r.entry.expected_route}**, got **{r.decision.route}** — "
            f"{r.decision.reason}"
        )
    lines.append("")
    return "\n".join(lines)


@dataclass
class CompareReport:
    """Two capability runs, same golden set, different prompt versions (Step 27)."""

    a: EvalReport
    b: EvalReport
    version_a: str
    version_b: str
    flipped: list[tuple]  # (entry, route_a, route_b)

    @property
    def delta(self) -> float:
        return self.b.agreement - self.a.agreement


def run_compare(judge_a, judge_b, path: str | Path = GOLDEN_PATH) -> CompareReport:
    ra = run_capability(judge_a, path)
    rb = run_capability(judge_b, path)
    flipped = [
        (a.entry, a.decision.route, b.decision.route)
        for a, b in zip(ra.results, rb.results, strict=True)
        if a.decision.route != b.decision.route
    ]
    return CompareReport(
        a=ra,
        b=rb,
        version_a=getattr(judge_a, "prompt_version", None) or "A",
        version_b=getattr(judge_b, "prompt_version", None) or "B",
        flipped=flipped,
    )


def render_compare_markdown(report: CompareReport, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    lines = [
        f"# Prompt compare — `{report.version_a}` vs `{report.version_b}`",
        "",
        f"_{now:%Y-%m-%d %H:%M} UTC — golden set, backend "
        f"`{report.a.backend}` vs `{report.b.backend}`_",
        "",
        "| version | agreement |",
        "|---|---|",
        f"| {report.version_a} | {report.a.agreement:.1%} ({report.a.agreed}/{report.a.total}) |",
        f"| {report.version_b} | {report.b.agreement:.1%} ({report.b.agreed}/{report.b.total}) |",
        "",
        f"**Agreement delta: {report.delta:+.1%}** · {len(report.flipped)} flipped samples",
        "",
        "## Flipped samples",
        "",
    ]
    if not report.flipped:
        lines.append("_none — the change is routing-neutral on the golden set_")
    for entry, route_a, route_b in report.flipped:
        lines.append(
            f"- `{entry.event['id']}` [{entry.event['topic']}] "
            f"{route_a} → {route_b} (expected {entry.expected_route}) — {entry.rationale}"
        )
    lines.append("")
    return "\n".join(lines)


def _writable_dir(out_dir: str | Path) -> Path:
    """eval/reports/ in a checkout; ~/.chief/eval-reports when installed read-only."""
    import os

    out_dir = Path(out_dir)
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        if os.access(out_dir, os.W_OK):
            return out_dir
    except OSError:
        pass
    from core.config import chief_home

    fallback = chief_home() / "eval-reports"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def write_compare_report(report: CompareReport, out_dir: str | Path = REPORTS_DIR) -> Path:
    out_dir = _writable_dir(out_dir)
    path = out_dir / f"compare-{report.version_a}-vs-{report.version_b}.md"
    path.write_text(render_compare_markdown(report), encoding="utf-8")
    return path


def write_report(report: EvalReport, out_dir: str | Path = REPORTS_DIR) -> Path:
    out_dir = _writable_dir(out_dir)
    stamp = datetime.now(UTC).strftime("%Y%m%d")
    path = out_dir / f"{report.kind}-{report.backend}-{stamp}.md"
    path.write_text(render_markdown(report), encoding="utf-8")
    return path
