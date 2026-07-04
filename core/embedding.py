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


DEFAULT_EMBEDDER: Embedder = HashEmbedder()
