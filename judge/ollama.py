"""Implements SPEC §4.4 stage 3: Ollama judge backend (local, no key)."""

from judge.base import HTTPJudge, JudgeUsage


class OllamaJudge(HTTPJudge):
    name = "ollama"
    base_url = "http://localhost:11434"

    async def _complete(self, client, messages: list[dict], retry: bool) -> tuple[str, JudgeUsage]:
        resp = await client.post(
            f"{self.base_url}/api/chat",
            json={
                "model": self.model,
                "messages": messages,
                "format": "json",
                "stream": False,
                "options": {"temperature": 0},
            },
        )
        resp.raise_for_status()
        body = resp.json()
        usage = JudgeUsage(
            tokens_in=body.get("prompt_eval_count", 0),
            tokens_out=body.get("eval_count", 0),
        )
        return body["message"]["content"], usage
