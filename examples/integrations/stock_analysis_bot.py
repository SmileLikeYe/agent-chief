"""A daily_stock_analysis-style bot routed through Chief as the judgment layer.

The ecosystem position this demonstrates: noisy upstream agents produce
everything they notice; Chief decides what deserves a human. Run it:

    python examples/integrations/stock_analysis_bot.py

Fully offline (fixture feed, in-memory state). With no LLM configured, rules
still kill the noise and everything else lands in the digest with
degraded=true — connect a backend in ~/.chief/config.toml for real scoring.
"""

import asyncio
import json
from pathlib import Path

from core.brain import judge_once

FEED = json.loads((Path(__file__).parent / "stock_feed.json").read_text(encoding="utf-8"))


async def main() -> None:
    print(f"{len(FEED)} analyst-bot reports in →\n")
    for payload in FEED:
        decision = await judge_once(dict(payload))  # the same pipeline `chief lite` runs
        mark = "🗑" if decision.route == "drop" else "📰"
        print(f"{mark} {payload['summary'][:66]:66} → {decision.route:8} "
              f"({decision.reason[:60]})")
    print("\nThe user saw none of this directly — the digest gets the survivors.")


if __name__ == "__main__":
    asyncio.run(main())
