"""Implements SPEC §4.4 stage 3: Anthropic judge backend (messages API)."""

from judge.base import HTTPJudge


class AnthropicJudge(HTTPJudge):
    name = "anthropic"
    base_url = "https://api.anthropic.com"

    async def _complete(self, client, messages: list[dict], retry: bool) -> str:
        system = messages[0]["content"]
        rest = [
            {"role": m["role"] if m["role"] == "user" else "user", "content": m["content"]}
            for m in messages[1:]
        ]
        resp = await client.post(
            f"{self.base_url}/v1/messages",
            headers={"x-api-key": self.api_key or "", "anthropic-version": "2023-06-01"},
            json={
                "model": self.model,
                "system": system,
                "messages": rest,
                "max_tokens": 512,
                "temperature": 0,
            },
        )
        resp.raise_for_status()
        return "".join(b["text"] for b in resp.json()["content"] if b.get("type") == "text")
