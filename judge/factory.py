"""Implements SPEC §4.4 stage 3: config-driven judge backend selection ([llm] in config.toml)."""

from judge.base import Judge


def make_judge(llm_config: dict) -> Judge:
    backend = llm_config.get("backend", "fixtures")
    model = llm_config.get("model", "")
    api_key = llm_config.get("api_key")
    base_url = llm_config.get("base_url")
    version = llm_config.get("prompt_version")

    if backend == "fixtures":
        from judge.fixtures import FixtureJudge

        return FixtureJudge({})
    if backend == "ollama":
        from judge.ollama import OllamaJudge

        return OllamaJudge(model or "qwen3:4b", base_url=base_url, prompt_version=version)
    if backend == "deepseek":
        from judge.deepseek import DeepSeekJudge

        return DeepSeekJudge(
            model or "deepseek-chat", api_key=api_key, base_url=base_url,
            prompt_version=version,
        )
    if backend == "anthropic":
        from judge.anthropic import AnthropicJudge

        return AnthropicJudge(
            model or "claude-haiku-4-5", api_key=api_key, base_url=base_url,
            prompt_version=version,
        )
    if backend == "openai":
        from judge.openai import OpenAIJudge

        return OpenAIJudge(
            model or "gpt-4o-mini", api_key=api_key, base_url=base_url,
            prompt_version=version,
        )
    raise ValueError(f"unknown llm backend: {backend!r}")
