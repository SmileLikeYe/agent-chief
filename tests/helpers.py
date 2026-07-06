"""Shared test factories."""

from datetime import UTC, datetime

from core.brain import Brain
from judge.base import JudgeResult

# Fixed daytime instant so tests never drift into quiet hours (23:00-08:00 UTC)
# when the suite happens to run at night.
FIXED_NOW = datetime(2026, 7, 6, 14, 0, tzinfo=UTC)


class StaticJudge:
    """Deterministic judge for pipeline tests."""

    name = "static"
    prompt_version = None  # declared → decisions get stamped with the active version

    def __init__(self, **overrides):
        self.overrides = overrides

    async def judge(self, event, context) -> JudgeResult:
        base = dict(
            urgency=0.7,
            relevance=0.7,
            actionability=0.7,
            novelty=0.7,
            confidence=0.7,
            dispatchable=False,
            dispatch_goal=None,
            memorize=None,
            reason="static judge",
        )
        base.update(self.overrides)
        return JudgeResult(**base)


def make_brain(state, tmp_path, judge=None, **kw) -> Brain:
    kw.setdefault("now_fn", lambda: FIXED_NOW)
    return Brain(
        state,
        judge or StaticJudge(),
        policy_path=tmp_path / "POLICY.md",
        **kw,
    )
