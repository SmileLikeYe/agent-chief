"""Implements SPEC §4.1: MCP server (fastmcp) — tools propose, feedback,
digest, policy, stats. Downstream agents call propose and obey the Decision."""

from datetime import UTC, datetime
from pathlib import Path

from fastmcp import FastMCP

from core.brain import Brain
from core.learner import apply_feedback, build_tact_report


def create_mcp(brain: Brain) -> FastMCP:
    mcp = FastMCP("chief")

    @mcp.tool
    async def propose(event: dict) -> dict:
        """Submit a candidate event; returns Chief's Decision. Obey it: do NOT
        message the user directly."""
        decision = await brain.process(event)
        return decision.model_dump(mode="json")

    @mcp.tool
    async def feedback(event_id: str, signal: str) -> str:
        """Record a user-reaction signal and learn from it. Signals include the
        natural should_interrupt / should_not_interrupt, plus acted / read /
        dismissed_fast / muted / task_ok / task_fail."""
        try:
            learned = await apply_feedback(
                brain.state, event_id, signal, datetime.now(UTC),
                classifier=brain.classifier,
            )
        except ValueError as exc:
            return f"error: {exc}"
        return "learned" if learned else "recorded"

    @mcp.tool
    async def digest(now: bool = False) -> dict:
        """Digest queue status; now=True asks chief to send it at the next tick."""
        counts = await brain.state.route_counts()
        return {"pending_digest_items": counts.get("digest", 0), "send_now": now}

    @mcp.tool
    async def policy(action: str = "show", text: str | None = None) -> str:
        """show → current POLICY.md; edit → append a line (takes effect immediately)."""
        path = Path(brain.policy_path)
        if action == "edit" and text:
            existing = path.read_text(encoding="utf-8") if path.exists() else "# POLICY\n"
            path.write_text(existing.rstrip() + f"\n{text}\n", encoding="utf-8")
        return path.read_text(encoding="utf-8") if path.exists() else ""

    @mcp.tool
    async def stats(days: int = 7) -> dict:
        """Tact-report numbers for the last N days."""
        report = await build_tact_report(brain.state, days=days, now=datetime.now(UTC))
        return {
            "days": report.days,
            "events_in": report.events_in,
            "blocked": report.blocked,
            "batched": report.batched,
            "handled": report.handled,
            "interrupted": report.interrupted,
        }

    return mcp
