"""Implements SPEC §4.4 stage 3: OpenAI judge backend (chat completions, JSON mode)."""

from judge.base import HTTPJudge


class OpenAIJudge(HTTPJudge):
    name = "openai"
    base_url = "https://api.openai.com/v1"

    async def _complete(self, client, messages: list[dict], retry: bool) -> str:
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
        return resp.json()["choices"][0]["message"]["content"]
