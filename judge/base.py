"""Implements SPEC §4.4 stage 3: judge backend interface and result model."""

from dataclasses import dataclass, field
from typing import Protocol

from pydantic import BaseModel, Field

from core.schema import Event


class JudgeResult(BaseModel):
    """The exact JSON the judge prompt demands (SPEC §4.4)."""

    urgency: float = Field(ge=0, le=1)
    relevance: float = Field(ge=0, le=1)
    actionability: float = Field(ge=0, le=1)
    novelty: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    dispatchable: bool = False
    dispatch_goal: str | None = None
    memorize: str | None = None
    reason: str


@dataclass
class JudgeContext:
    """The semi-stable + per-call prompt context (SPEC §4.4)."""

    user_profile: str = ""
    recent_deliveries: list[str] = field(default_factory=list)
    associated_memory: list[str] = field(default_factory=list)
    scene: str = "idle"
    scene_confidence: float = 0.4


class Judge(Protocol):
    name: str

    async def judge(self, event: Event, context: JudgeContext | None) -> JudgeResult: ...
