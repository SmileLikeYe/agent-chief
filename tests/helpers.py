"""Shared test factories."""

from core.brain import Brain
from judge.base import JudgeResult


class StaticJudge:
    """Deterministic judge for pipeline tests."""

    name = "static"

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
    return Brain(
        state,
        judge or StaticJudge(),
        policy_path=tmp_path / "POLICY.md",
        **kw,
    )
