"""Implements SPEC §4.4 stage 3: judge backend interface and result model."""

import json
from dataclasses import dataclass, field
from typing import Protocol

from pydantic import BaseModel, Field

from core.schema import Event


class JudgeUsage(BaseModel):
    """Token accounting read from the backend's API usage fields (Step 26)."""

    tokens_in: int = 0
    tokens_out: int = 0
    cached_tokens: int = 0


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
    usage: JudgeUsage | None = None  # set by the transport layer, not the LLM


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


class JudgeError(RuntimeError):
    """The backend could not produce a valid JudgeResult (after retries).

    Carries `usage`: the tokens paid across all failed attempts, so the
    degraded path can still bill them (Step 26)."""

    def __init__(self, message: str, usage: "JudgeUsage | None" = None):
        super().__init__(message)
        self.usage = usage


def extract_json(text: str) -> str:
    """Strip markdown code fences and surrounding chatter around a JSON object."""
    text = text.strip()
    if "```" in text:
        inner = text.split("```", 2)[1]
        text = inner.removeprefix("json").strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"no JSON object in judge output: {text[:80]!r}")
    return text[start : end + 1]


class HTTPJudge:
    """Shared skeleton for HTTP judge backends: prompt assembly, JSON-mode
    parsing, one retry on malformed output (SPEC §9 Step 8)."""

    name = "http"
    MAX_ATTEMPTS = 2

    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        base_url: str | None = None,
        transport=None,
        timeout: float = 60.0,
        prompt_version: str | None = None,
    ):
        self.model = model
        self.api_key = api_key
        self.prompt_version = prompt_version  # None → the active PROMPT_VERSION
        if base_url:
            self.base_url = base_url
        self._transport = transport
        self.timeout = timeout

    def _client(self):
        import httpx

        return httpx.AsyncClient(transport=self._transport, timeout=self.timeout)

    async def _complete(self, client, messages: list[dict], retry: bool) -> tuple[str, JudgeUsage]:
        """Return (assistant text, token usage read from the API response)."""
        raise NotImplementedError

    async def judge(self, event: Event, context: JudgeContext | None) -> JudgeResult:
        from judge import prompts

        ctx = context or JudgeContext()
        v = self.prompt_version
        messages = [
            {"role": "system", "content": prompts.render_static("system", version=v)},
            {"role": "system", "content": prompts.context_block(ctx, version=v)},
            {"role": "user", "content": prompts.user_block(event, ctx, version=v)},
        ]
        last_error: Exception | None = None
        total = JudgeUsage()
        async with self._client() as client:
            for attempt in range(self.MAX_ATTEMPTS):
                try:
                    raw, usage = await self._complete(client, messages, retry=attempt > 0)
                except Exception as exc:
                    # transport failure mid-retry: tokens already paid still bill
                    raise JudgeError(
                        f"{self.name}: transport failure on attempt {attempt + 1}: {exc}",
                        usage=total,
                    ) from exc
                total = JudgeUsage(
                    tokens_in=total.tokens_in + usage.tokens_in,
                    tokens_out=total.tokens_out + usage.tokens_out,
                    cached_tokens=total.cached_tokens + usage.cached_tokens,
                )
                try:
                    data = json.loads(extract_json(raw))
                    if isinstance(data, dict):
                        data.pop("usage", None)  # transport-owned; never trust the LLM's echo
                    result = JudgeResult.model_validate(data)
                    result.usage = total  # retries included: the user pays for them too
                    return result
                except Exception as exc:
                    last_error = exc
                    messages = [
                        *messages,
                        {"role": "user", "content": prompts.render_static("retry", version=v)},
                    ]
        raise JudgeError(
            f"{self.name}: malformed judge output after retries", usage=total
        ) from last_error
