"""Per-backend price table and cost math (SPEC v3.1 Step 26).

USD per 1M tokens. DeepSeek models its context cache explicitly: input tokens
served from cache cost a fraction of a cache miss — the whole reason Chief's
stable-prefix prompt layout exists. Prices are the published list rates at the
time of writing; adjust here, nowhere else.
"""

PRICES: dict[str, dict[str, float]] = {
    # deepseek-chat (V3): cache-hit input is ~4x cheaper than miss
    "deepseek": {"input_cache_miss": 0.27, "input_cache_hit": 0.07, "output": 1.10},
    # gpt-4o list prices; cached input is half price
    "openai": {"input_cache_miss": 2.50, "input_cache_hit": 1.25, "output": 10.00},
    # claude sonnet list prices; cache reads are 10% of base input
    "anthropic": {"input_cache_miss": 3.00, "input_cache_hit": 0.30, "output": 15.00},
    # local / offline backends are free
    "ollama": {"input_cache_miss": 0.0, "input_cache_hit": 0.0, "output": 0.0},
    "fixtures": {"input_cache_miss": 0.0, "input_cache_hit": 0.0, "output": 0.0},
}
_FREE = PRICES["fixtures"]


def usd_cost(backend: str, tokens_in: int, tokens_out: int, cached: int = 0) -> float:
    """Cost in USD for one judgment; unknown backends are treated as free."""
    p = PRICES.get(backend, _FREE)
    cached = min(cached, tokens_in)
    return (
        (tokens_in - cached) / 1e6 * p["input_cache_miss"]
        + cached / 1e6 * p["input_cache_hit"]
        + tokens_out / 1e6 * p["output"]
    )
