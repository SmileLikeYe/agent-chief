"""Regenerate every number on the README first screen (SPEC v3.1 Step 31).

    python scripts/readme_metrics.py          # print the metrics block
    python scripts/readme_metrics.py --write  # splice it into README.md

Sources: the deterministic demo replay (24 events, the same pipeline
production runs) and the v1 prompt templates + published price table for the
cost projection. No network, no keys — anyone can reproduce these.
"""

import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from eval.runner import run_regression  # noqa: E402
from judge import prompts  # noqa: E402
from judge.pricing import PRICES  # noqa: E402

README = Path(__file__).parent.parent / "README.md"
MARKER = re.compile(r"(<!-- metrics:start -->\n).*?(<!-- metrics:end -->)", re.DOTALL)


def tokens(text: str) -> int:
    return math.ceil(len(text) / 4)  # the standard ~4 chars/token estimate


def build_block() -> str:
    results = run_regression().results
    total = len(results)
    interrupts = sum(
        1 for r in results
        if r.decision.route == "interrupt" or r.entry.delivery == "interrupt"
    )
    judged = sum(1 for r in results if r.decision.stage == 3)
    blocked = sum(1 for r in results if r.decision.route == "drop")
    interception = 1 - interrupts / total
    llm_share = judged / total

    # cost projection: stable-prefix layout means [system]+[context] cache-hits
    # after the first call of the day; only the [user] block misses.
    system_t = tokens(prompts.SYSTEM_PROMPT)
    context_t = tokens("User profile: engineer\nRecently delivered: none\nAssociated memory: none")
    user_t = 120  # a typical candidate-event block, measured order of magnitude
    out_t = 90  # the judge's JSON verdict
    p = PRICES["deepseek"]
    cached, missed = system_t + context_t, user_t
    per_event = (
        cached / 1e6 * p["input_cache_hit"]
        + missed / 1e6 * p["input_cache_miss"]
        + out_t / 1e6 * p["output"]
    )
    per_1k = per_event * 1000 * llm_share  # rule-killed events never pay
    cache_rate = cached / (cached + missed)

    return (
        f"**{total} events in → {interrupts} interruption** "
        f"({interception:.0%} intercepted: {blocked} blocked outright, the rest batched, "
        f"dispatched, or remembered)\n"
        f"· only **{llm_share:.0%} of events ever reach the LLM** — the noisiest "
        f"{1 - llm_share:.0%} dies on hard rules in microseconds, for free\n"
        f"· stable-prefix prompts: **{cache_rate:.0%} of judge input tokens cache-hit** "
        f"(system + context blocks)\n"
        f"· projected judgment cost **${per_1k:.3f} per 1,000 events** "
        f"(DeepSeek list prices, cache-aware)\n\n"
        f"*(every number regenerates from the deterministic demo replay: "
        f"`make readme-metrics`)*\n"
    )


def main() -> None:
    block = build_block()
    if "--write" in sys.argv:
        text = README.read_text(encoding="utf-8")
        new = MARKER.sub(lambda m: m.group(1) + block + m.group(2), text)
        README.write_text(new, encoding="utf-8")
        print("README.md metrics block updated")
    else:
        print(block, end="")


if __name__ == "__main__":
    main()
