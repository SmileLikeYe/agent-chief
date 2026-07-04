"""Implements SPEC §4.4 stage 3: Ollama judge backend (local, no key)."""

from judge.base import HTTPJudge


class OllamaJudge(HTTPJudge):
    name = "ollama"
    base_url = "http://localhost:11434"

    async def _complete(self, client, messages: list[dict], retry: bool) -> str:
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
        return resp.json()["message"]["content"]
