"""Implements SPEC §4.3: clock provider — local time and quiet-hours flag, pure code."""

from collections.abc import Callable
from datetime import datetime
from typing import Any

from core.scorer import in_quiet_hours


class ClockProvider:
    name = "clock"

    def __init__(
        self,
        quiet_hours: str = "23:00-08:00",
        now_fn: Callable[[], datetime] = datetime.now,
    ):
        self.quiet_hours = quiet_hours
        self.now_fn = now_fn

    def sample(self) -> dict[str, Any]:
        now = self.now_fn()
        return {
            "local_time": now.isoformat(),
            "hour": now.hour,
            "weekend": now.weekday() >= 5,
            "quiet_hours": in_quiet_hours(now, self.quiet_hours),
        }
