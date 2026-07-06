"""Per-backend price table and cost math (SPEC v3.1 Step 26).

USD per 1M tokens. DeepSeek models its context cache explicitly: input tokens
served from cache cost a fraction of a cache miss — the whole reason Chief's
stable-prefix prompt layout exists. Prices are the published list rates at the
time of writing; adjust here, nowhere else.
"""

PRICES: dict[str, dict[str, float]] = {
    # backend-level fallbacks (used when the model has no entry below)
    "deepseek": {"input_cache_miss": 0.27, "input_cache_hit": 0.07, "output": 1.10},
    "openai": {"input_cache_miss": 2.50, "input_cache_hit": 1.25, "output": 10.00},
    "anthropic": {"input_cache_miss": 3.00, "input_cache_hit": 0.30, "output": 15.00},
    # local / offline backends are free
    "ollama": {"input_cache_miss": 0.0, "input_cache_hit": 0.0, "output": 0.0},
    "fixtures": {"input_cache_miss": 0.0, "input_cache_hit": 0.0, "output": 0.0},
}

# model-level list prices, matched by ordered substring — real model ids vary
# ("claude-3-5-haiku-20241022", "claude-haiku-4-5", …) so anchored prefixes
# miss them; a backend serves many models at very different rates
# (gpt-4o vs gpt-4o-mini is ~17x)
MODEL_PRICES: list[tuple[str, dict[str, float]]] = [
    ("deepseek-reasoner", {"input_cache_miss": 0.55, "input_cache_hit": 0.14, "output": 2.19}),
    ("deepseek", {"input_cache_miss": 0.27, "input_cache_hit": 0.07, "output": 1.10}),
    ("gpt-4o-mini", {"input_cache_miss": 0.15, "input_cache_hit": 0.075, "output": 0.60}),
    ("gpt-4o", {"input_cache_miss": 2.50, "input_cache_hit": 1.25, "output": 10.00}),
    ("haiku", {"input_cache_miss": 1.00, "input_cache_hit": 0.10, "output": 5.00}),
    ("sonnet", {"input_cache_miss": 3.00, "input_cache_hit": 0.30, "output": 15.00}),
    ("opus", {"input_cache_miss": 15.00, "input_cache_hit": 1.50, "output": 75.00}),
]
_FREE = PRICES["fixtures"]


def _table(backend: str, model: str | None) -> dict[str, float]:
    if model:
        for needle, table in MODEL_PRICES:  # ordered: most specific first
            if needle in model:
                return table
    return PRICES.get(backend, _FREE)


def usd_cost(
    backend: str, tokens_in: int, tokens_out: int, cached: int = 0, model: str | None = None
) -> float:
    """Cost in USD for one judgment; unknown backends/models are treated as free."""
    p = _table(backend, model)
    cached = min(cached, tokens_in)
    return (
        (tokens_in - cached) / 1e6 * p["input_cache_miss"]
        + cached / 1e6 * p["input_cache_hit"]
        + tokens_out / 1e6 * p["output"]
    )
