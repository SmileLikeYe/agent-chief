"""Implements SPEC §4.7: fixture judge backend — pre-recorded component scores
keyed by event id. Powers the fully offline demo; no keys, no network."""

import json
from pathlib import Path
from typing import Any

from judge.base import JudgeContext, JudgeResult


class FixtureJudge:
    name = "fixtures"

    def __init__(self, results: dict[str, dict[str, Any]]):
        self._results = results

    @classmethod
    def from_file(cls, path: str | Path) -> "FixtureJudge":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(data)

    async def judge(self, event, context: JudgeContext | None) -> JudgeResult:
        try:
            return JudgeResult.model_validate(self._results[event.id])
        except KeyError:
            raise LookupError(f"no fixture judge result for event {event.id}") from None
