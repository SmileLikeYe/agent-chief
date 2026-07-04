"""Implements SPEC §3: pydantic data models."""

import secrets
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

Route = Literal["interrupt", "digest", "dispatch", "curate", "drop"]
Scene = Literal["sleeping", "deep_work", "meeting", "commuting", "social", "leisure", "idle"]
Executor = Literal["claude_code", "openclaw", "shell", "noop"]


def new_event_id(at: datetime) -> str:
    """evt_{yyyymmdd}_{hhmm}_{4hex}, generated at ingest (SPEC §3)."""
    return f"evt_{at:%Y%m%d}_{at:%H%M}_{secrets.token_hex(2)}"


class Event(BaseModel):
    id: str
    source: str
    topic: str
    summary: str = Field(max_length=200)
    detail: str | None = None
    suggested_action: str | None = None
    evidence: list[str] = []
    claimed_urgency: Literal["low", "medium", "high"] | None = None
    expires_at: datetime | None = None
    dedup_key: str | None = None
    received_at: datetime


class Decision(BaseModel):
    event_id: str
    route: Route
    score: float | None = None
    components: dict[str, float] | None = None
    scene: str
    scene_confidence: float
    cost: float
    matched_rules: list[str] = []
    reason: str
    stage: int
    dispatch_task_id: str | None = None


class Task(BaseModel):
    id: str
    origin_event_id: str
    goal: str
    executor: Executor
    acceptance: str
    acceptance_cmd: str | None = None
    status: Literal["pending", "running", "done", "failed", "rejected"] = "pending"
    result_summary: str | None = None
    attempts: int = 0


class MemoryItem(BaseModel):
    id: str
    origin_event_id: str | None = None
    text: str
    topic: str
    embedding: list[float]
    created_at: datetime
    last_hit_at: datetime | None = None
    hit_count: int = 0
    ttl_days: int = 90


class SceneState(BaseModel):
    scene: Scene
    confidence: float
    signals: dict[str, Any]
    at: datetime
