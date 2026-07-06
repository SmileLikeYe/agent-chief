"""Implements SPEC §4.4 stage 3: OpenAI judge backend (chat completions, JSON mode)."""

from judge.base import HTTPJudge, JudgeUsage


class OpenAIJudge(HTTPJudge):
    name = "openai"
    base_url = "https://api.openai.com/v1"

    async def _complete(self, client, messages: list[dict], retry: bool) -> tuple[str, JudgeUsage]:
        resp = await client.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "messages": messages,
                "temperature": 0,
                "response_format": {"type": "json_object"},
            },
        )
        resp.raise_for_status()
        body = resp.json()
        u = body.get("usage") or {}  # some proxies send "usage": null
        usage = JudgeUsage(
            tokens_in=u.get("prompt_tokens", 0),
            tokens_out=u.get("completion_tokens", 0),
            # deepseek reports prompt_cache_hit_tokens; openai nests cached_tokens
            cached_tokens=u.get("prompt_cache_hit_tokens", 0)
            or (u.get("prompt_tokens_details") or {}).get("cached_tokens", 0),
        )
        return body["choices"][0]["message"]["content"], usage
