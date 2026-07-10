"""Implements SPEC §4.3: scene inference rules (pure rules, 30s cache) + scene policy table."""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Protocol

from core.schema import SceneState

logger = logging.getLogger(__name__)


class ContextProvider(Protocol):
    name: str

    def sample(self) -> dict[str, Any]: ...


def infer_scene(signals: dict[str, Any], *, now: datetime) -> SceneState:
    """SPEC §4.3 inference table, evaluated top to bottom; first match wins."""
    weekend = signals.get("weekend", now.weekday() >= 5)
    evening = now.hour >= 18
    daytime = 9 <= now.hour < 18

    scene, conf = "idle", 0.4
    if signals.get("quiet_hours") and signals.get("screen_locked") and (
        signals.get("locked_minutes", 0) > 30
    ):
        scene, conf = "sleeping", 0.9
    elif signals.get("calendar_now") == "meeting" or signals.get("foreground_kind") == "meeting":
        scene, conf = "meeting", 0.85
    elif signals.get("calendar_now") == "focus" or (
        signals.get("foreground_kind") == "ide"
        and signals.get("foreground_minutes", 0) > 25
        and signals.get("active")
    ):
        scene, conf = "deep_work", 0.75
    elif signals.get("calendar_now") == "commute":
        scene, conf = "commuting", 0.7
    elif signals.get("foreground_kind") == "entertainment" or (
        weekend and daytime and signals.get("idle_seconds", 0) > 300
    ):
        scene, conf = "leisure", 0.6
    elif signals.get("dnd_mode") == "personal" or (
        weekend and evening and signals.get("mobile_active")
    ):
        scene, conf = "social", 0.5

    return SceneState(scene=scene, confidence=conf, signals=signals, at=now)


def downgrade_low_confidence(route: str, scene: SceneState) -> str:
    """SPEC §4.3 / Principle 2: scene confidence < 0.6 downgrades interrupt → digest."""
    if route == "interrupt" and scene.confidence < 0.6:
        return "digest"
    return route


@dataclass(frozen=True)
class ScenePolicy:
    interrupt_threshold: float
    max_level: str  # delivery level cap: terminal < desktop < silent < vibrate < ring
    night_outside_whitelist_to_digest: bool = False


# SPEC §4.3 defaults; interrupt thresholds overridable via POLICY.md "## Scene thresholds".
SCENE_POLICY: dict[str, ScenePolicy] = {
    "sleeping": ScenePolicy(0.95, "ring", night_outside_whitelist_to_digest=True),
    "meeting": ScenePolicy(0.90, "silent"),
    "deep_work": ScenePolicy(0.85, "silent"),
    "commuting": ScenePolicy(0.60, "ring"),
    "social": ScenePolicy(0.70, "vibrate"),
    "leisure": ScenePolicy(0.50, "vibrate"),
    "idle": ScenePolicy(0.45, "ring"),
}


def interrupt_threshold(scene: str, overrides: dict[str, float] | None = None) -> float:
    if overrides and scene in overrides:
        return overrides[scene]
    return SCENE_POLICY[scene].interrupt_threshold


class SceneEngine:
    """Samples all providers, merges signals, infers the scene; 30s result cache."""

    CACHE_SECONDS = 30

    def __init__(
        self,
        providers: list[ContextProvider],
        now_fn: Callable[[], datetime] = lambda: datetime.now().astimezone(),
    ):
        self.providers = providers
        self.now_fn = now_fn
        self._cached: SceneState | None = None

    def current(self) -> SceneState:
        now = self.now_fn()
        if self._cached and now - self._cached.at < timedelta(seconds=self.CACHE_SECONDS):
            return self._cached
        signals: dict[str, Any] = {}
        for provider in self.providers:
            try:
                signals.update(provider.sample())
            except Exception as exc:  # graceful degradation: unavailable → skip
                logger.debug("provider %s unavailable: %s", provider.name, exc)
        self._cached = infer_scene(signals, now=now)
        return self._cached
