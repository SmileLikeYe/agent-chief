"""Calibration eval (SPEC v3.x): is the routing score a *trustworthy* decision
variable, and are the per-scene interrupt thresholds sensible operating points?

Chief routes on `score ≥ scene-threshold`. A skeptic asks two fair questions:
does a higher score really mean the user is more likely to want the interrupt
(**discrimination**), and does a given score value mean what it says
(**calibration**)? Both are answerable offline with real errors — the cohort's
held-out stream (`eval/cohort.py`) makes genuine interrupt predictions against
each persona's *hidden* preferences, so ~7k `(score, wanted)` pairs with real
mistakes fall out of it for free.

We report, pooled across the 100 users, post-learning:

  AUC            rank-based, assumption-free: P(score_wanted > score_unwanted).
  reliability    empirical P(wanted) per score bin — does it rise with score?
  ECE            expected calibration error of the raw score as a probability,
                 and after a monotone (isotonic) recalibration — a fitted map is
                 measurement, not a production path, exactly like this harness.
  operating pts  where each scene's threshold sits, and the precision/recall it
                 buys — high-bar scenes trade recall for precision on purpose.

Deterministic and offline (it is a view over `run_cohort()`), so the numbers are
pinned in tests like every other eval.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from context.infer import interrupt_threshold
from core.scorer import DIMS
from eval.cohort import WEIGHT_CAP, run_cohort

# score = Σ_dim w[dim]·comp[dim]; comps ≤ 1 and learned weights cap at WEIGHT_CAP,
# so the score's structural maximum is len(DIMS)·WEIGHT_CAP. We map score→[0,1] by
# this fixed, disclosed constant to read it as a probability — the honest naive
# baseline the isotonic step then improves on.
SCORE_MAX = len(DIMS) * WEIGHT_CAP  # 5 · 0.5 = 2.5


def _p(score: float) -> float:
    return min(1.0, max(0.0, score / SCORE_MAX))


def auc(pairs: list[tuple[float, bool]]) -> float:
    """Mann-Whitney U / ROC-AUC with tie-averaged ranks. No probability mapping —
    pure ranking, so it needs no normalization assumption."""
    pos = [s for s, w in pairs if w]
    neg = [s for s, w in pairs if not w]
    if not pos or not neg:
        return float("nan")
    ordered = sorted(s for s, _ in pairs)
    # average rank of each score value (1-based), handling ties
    rank_of: dict[float, float] = {}
    i = 0
    while i < len(ordered):
        j = i
        while j + 1 < len(ordered) and ordered[j + 1] == ordered[i]:
            j += 1
        avg = (i + j) / 2 + 1  # mean of 1-based ranks in the tie block
        rank_of[ordered[i]] = avg
        i = j + 1
    rank_sum_pos = sum(rank_of[s] for s in pos)
    n_pos, n_neg = len(pos), len(neg)
    return (rank_sum_pos - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)


@dataclass
class Bin:
    lo: float
    hi: float
    n: int
    mean_p: float
    frac_wanted: float


def reliability(pairs: list[tuple[float, bool]], bins: int = 10) -> list[Bin]:
    """Equal-width bins over p = score/SCORE_MAX; empirical P(wanted) per bin."""
    buckets: list[list[tuple[float, bool]]] = [[] for _ in range(bins)]
    for score, wanted in pairs:
        p = _p(score)
        idx = min(bins - 1, int(p * bins))
        buckets[idx].append((p, wanted))
    out = []
    for b, items in enumerate(buckets):
        if not items:
            continue
        out.append(Bin(
            lo=b / bins, hi=(b + 1) / bins, n=len(items),
            mean_p=sum(p for p, _ in items) / len(items),
            frac_wanted=sum(1 for _, w in items if w) / len(items),
        ))
    return out


def ece_from_bins(rows: list[Bin], total: int) -> float:
    return sum(r.n / total * abs(r.frac_wanted - r.mean_p) for r in rows) if total else 0.0


def _ece_prob(prob_pairs: list[tuple[float, bool]], bins: int = 10) -> float:
    """ECE over (probability, wanted) pairs — bins directly on the probability."""
    buckets: list[list[tuple[float, bool]]] = [[] for _ in range(bins)]
    for p, w in prob_pairs:
        buckets[min(bins - 1, int(p * bins))].append((p, w))
    total = len(prob_pairs)
    if not total:
        return 0.0
    e = 0.0
    for items in buckets:
        if not items:
            continue
        mp = sum(p for p, _ in items) / len(items)
        fw = sum(1 for _, w in items if w) / len(items)
        e += len(items) / total * abs(fw - mp)
    return e


def _isotonic(xs: list[float], ys: list[float]) -> list[tuple[float, float]]:
    """Pool-adjacent-violators: the monotone non-decreasing step fit of ys on
    sorted xs. Returns (x, fitted_y) knots. Trivial, parameter-free — not ML."""
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    xs = [xs[i] for i in order]
    ys = [ys[i] for i in order]
    # each block: [value, weight]
    blocks: list[list[float]] = []
    for y in ys:
        blocks.append([y, 1.0])
        while len(blocks) > 1 and blocks[-2][0] > blocks[-1][0]:
            (v2, w2), (v1, w1) = blocks.pop(), blocks.pop()
            blocks.append([(v1 * w1 + v2 * w2) / (w1 + w2), w1 + w2])
    fitted: list[float] = []
    for value, weight in blocks:
        fitted.extend([value] * int(weight))
    return list(zip(xs, fitted, strict=True))


def isotonic_ece(pairs: list[tuple[float, bool]], bins: int = 10) -> float:
    """ECE after fitting a monotone recalibration on one half and scoring the
    held-out other half — a fitted map that must generalize, not memorize. The
    halves are interleaved (not split by score) so both see the full range."""
    train = [pairs[i] for i in range(len(pairs)) if i % 2 == 0]
    test = [pairs[i] for i in range(len(pairs)) if i % 2 == 1]
    if not train or not test:
        return float("nan")
    knots = _isotonic([_p(s) for s, _ in train], [1.0 if w else 0.0 for _, w in train])
    kx = [x for x, _ in knots]
    ky = [y for _, y in knots]

    def calibrated(p: float) -> float:
        import bisect

        i = bisect.bisect_right(kx, p) - 1  # last knot with x ≤ p
        return ky[max(0, min(i, len(ky) - 1))]

    return _ece_prob([(calibrated(_p(s)), w) for s, w in test], bins=bins)


@dataclass
class SceneOperatingPoint:
    scene: str
    threshold: float
    precision: float
    recall: float
    n: int


@dataclass
class CalibrationReport:
    n_events: int
    frac_wanted: float
    auc_before: float
    auc_after: float
    bins: list[Bin]
    ece_raw: float
    ece_isotonic: float
    operating_points: list[SceneOperatingPoint]

    @property
    def monotone(self) -> bool:
        fr = [b.frac_wanted for b in self.bins]
        return all(a <= b + 1e-9 for a, b in zip(fr, fr[1:], strict=False))


def _operating_points(by_scene: dict[str, list[tuple[float, bool]]]) -> list[SceneOperatingPoint]:
    pts = []
    for scene, pairs in sorted(by_scene.items(), key=lambda kv: interrupt_threshold(kv[0])):
        thr = interrupt_threshold(scene)
        tp = sum(1 for s, w in pairs if s >= thr and w)
        fp = sum(1 for s, w in pairs if s >= thr and not w)
        fn = sum(1 for s, w in pairs if s < thr and w)
        precision = tp / (tp + fp) if (tp + fp) else 1.0
        recall = tp / (tp + fn) if (tp + fn) else 1.0
        pts.append(SceneOperatingPoint(scene, thr, precision, recall, len(pairs)))
    return pts


async def run_calibration() -> CalibrationReport:
    report = await run_cohort()
    after: list[tuple[float, bool]] = []
    before: list[tuple[float, bool]] = []
    by_scene: dict[str, list[tuple[float, bool]]] = {}
    for r in report.results:
        after.extend(r.eval_scores_after)
        before.extend(r.eval_scores_before)
        by_scene.setdefault(r.scene, []).extend(r.eval_scores_after)

    rows = reliability(after)
    return CalibrationReport(
        n_events=len(after),
        frac_wanted=sum(1 for _, w in after if w) / len(after) if after else 0.0,
        auc_before=auc(before),
        auc_after=auc(after),
        bins=rows,
        ece_raw=ece_from_bins(rows, len(after)),
        ece_isotonic=isotonic_ece(after),
        operating_points=_operating_points(by_scene),
    )


def render_markdown(report: CalibrationReport, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    bar = lambda v: "█" * round(v * 20)  # noqa: E731
    lines = [
        "# Calibration eval — is the routing score trustworthy?",
        "",
        f"_{now:%Y-%m-%d %H:%M} UTC · {report.n_events} held-out interrupt "
        f"predictions pooled across the 100-user cohort · {report.frac_wanted:.0%} "
        "wanted_",
        "",
        f"**The score ranks wanted above unwanted with AUC {report.auc_after:.3f}** "
        f"after learning (up from {report.auc_before:.3f} on uniform weights). "
        f"Empirical P(wanted) is {'monotone' if report.monotone else 'not monotone'} "
        f"in the score; a monotone recalibration cuts ECE "
        f"{report.ece_raw:.3f} → {report.ece_isotonic:.3f}.",
        "",
        "## Reliability — P(wanted) by score bin",
        "",
        "Score mapped to [0,1] by its structural max "
        f"({len(DIMS)}·{WEIGHT_CAP} = {SCORE_MAX}). A well-ordered decision "
        "variable climbs monotonically here.",
        "",
        "```",
        "  score bin      P(wanted)              n",
    ]
    for b in report.bins:
        lines.append(
            f"  {b.lo:.1f}–{b.hi:.1f}   |{bar(b.frac_wanted):<20}| "
            f"{b.frac_wanted:>4.0%}  ({b.n})"
        )
    lines += [
        "```",
        "",
        f"- **AUC after learning: {report.auc_after:.3f}** (before: "
        f"{report.auc_before:.3f}) — assumption-free ranking quality; learning "
        "turns the score into a strong interrupt discriminator.",
        f"- **ECE raw: {report.ece_raw:.3f} → isotonic: {report.ece_isotonic:.3f}** — "
        "the raw score is well-ordered but not natively a probability; a "
        "parameter-free monotone map (fit on half, scored on the held-out half) "
        "makes it calibrated.",
        "",
        "## Per-scene operating points",
        "",
        "Each scene's interrupt threshold is a deliberate point on the same score "
        "axis — quieter scenes sit lower (more recall), demanding scenes sit higher "
        "(more precision):",
        "",
        "| scene | threshold | precision | recall | n |",
        "|---|---|---|---|---|",
    ]
    for op in report.operating_points:
        lines.append(
            f"| {op.scene} | {op.threshold:.2f} | {op.precision:.0%} | "
            f"{op.recall:.0%} | {op.n} |"
        )
    lines += [
        "",
        "## Method & honesty",
        "",
        "- A view over `run_cohort()`: same seeded, offline held-out stream, so "
        "these numbers are byte-stable and pinned in `tests/test_calibration.py`.",
        "- **AUC needs no probability assumption** — it is pure rank order, the "
        "cleanest claim here. The reliability/ECE numbers depend on the disclosed "
        f"score→[0,1] map (÷{SCORE_MAX}); the isotonic step removes that dependence "
        "by *learning* the map and is scored on held-out data so it can't memorize.",
        "- Isotonic PAV is a parameter-free monotone fit used only to measure "
        "calibratability — it is not added to the routing path (SPEC §13: no heavy "
        "ML; the shipped router stays score-vs-threshold).",
        "",
    ]
    return "\n".join(lines)


def write_report(report: CalibrationReport, out_dir: str | Path | None = None) -> Path:
    from eval.runner import REPORTS_DIR, _writable_dir

    out_dir = _writable_dir(out_dir or REPORTS_DIR)
    path = out_dir / "calibration.md"
    path.write_text(render_markdown(report), encoding="utf-8")
    return path
