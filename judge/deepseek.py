"""Implements SPEC §4.4 stage 3: DeepSeek judge backend (OpenAI-compatible API)."""

from judge.openai import OpenAIJudge


class DeepSeekJudge(OpenAIJudge):
    name = "deepseek"
    base_url = "https://api.deepseek.com"
