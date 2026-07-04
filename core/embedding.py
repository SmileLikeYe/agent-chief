"""Implements SPEC §4.4/§4.5: pluggable text embeddings.

The default `HashEmbedder` is a deterministic, dependency-free hashed bag-of-words
vectorizer — good enough for stage-1 canned-set similarity and the offline demo.
Step 9 wires `sentence-transformers` behind the same interface.
"""

import hashlib
import math
import re
from typing import Protocol

_DIM = 256
_TOKEN_RE = re.compile(r"[a-z0-9]+")


class Embedder(Protocol):
    def embed(self, text: str) -> list[float]: ...


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class HashEmbedder:
    """Deterministic hashed bag-of-words embedding (no model download)."""

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * _DIM
        for token in _TOKEN_RE.findall(text.lower()):
            h = int.from_bytes(hashlib.md5(token.encode()).digest()[:4], "big")
            vec[h % _DIM] += 1.0
        return vec


class SentenceTransformerEmbedder:
    """Real local embedding model (SPEC §4.5): bge-small-en-v1.5 by default,
    bge-m3 for mixed Chinese-English. Requires the `embeddings` extra."""

    _MODEL_ALIASES = {
        "bge-small-en-v1.5": "BAAI/bge-small-en-v1.5",
        "bge-m3": "BAAI/bge-m3",
    }

    def __init__(self, model: str = "bge-small-en-v1.5"):
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(self._MODEL_ALIASES.get(model, model))

    def embed(self, text: str) -> list[float]:
        return self._model.encode(text, normalize_embeddings=True).tolist()


def make_embedder(config: dict) -> Embedder:
    """Config-driven embedder selection; degrades to HashEmbedder with a warning
    when sentence-transformers (optional `embeddings` extra) is unavailable."""
    import logging

    name = config.get("embedding_model", "hash")
    if name == "hash":
        return HashEmbedder()
    try:
        return SentenceTransformerEmbedder(name)
    except ImportError:
        logging.getLogger(__name__).warning(
            "sentence-transformers not installed (uv sync --extra embeddings); "
            "falling back to hash embeddings"
        )
        return HashEmbedder()


DEFAULT_EMBEDDER: Embedder = HashEmbedder()
