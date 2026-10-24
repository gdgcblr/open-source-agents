"""Shared FastEmbed ONNX embedder with a bounded, thread-safe vector cache."""

from __future__ import annotations

import threading
from collections import OrderedDict
from collections.abc import Callable, Sequence

from adk_memshield import MemShieldEmbedder

EmbedFn = Callable[[Sequence[str]], list[list[float]]]

# Bounded LRU so arbitrary user-supplied queries cannot grow process memory without limit.
_VECTOR_CACHE_MAX = 4096
_VECTOR_CACHE: OrderedDict[str, list[float]] = OrderedDict()
_VECTOR_CACHE_LOCK = threading.Lock()
_RAW_EMBEDDER: MemShieldEmbedder | None = None
_RAW_EMBEDDER_LOCK = threading.Lock()


def get_cached_embed_fn(model_name: str = "BAAI/bge-small-en-v1.5", dim: int = 384) -> EmbedFn:
    """Return an embedding callable backed by FastEmbed ONNX with in-memory vector caching."""
    global _RAW_EMBEDDER
    with _RAW_EMBEDDER_LOCK:
        if _RAW_EMBEDDER is None:
            _RAW_EMBEDDER = MemShieldEmbedder(model_name=model_name, expected_dim=dim)
        embedder = _RAW_EMBEDDER

    def _embed(texts: Sequence[str]) -> list[list[float]]:
        results: dict[str, list[float]] = {}
        missing: list[str] = []
        with _VECTOR_CACHE_LOCK:
            for t in texts:
                if t in _VECTOR_CACHE:
                    _VECTOR_CACHE.move_to_end(t)
                    results[t] = _VECTOR_CACHE[t]
                elif t not in missing:
                    missing.append(t)
        if missing:
            computed = embedder.embed_documents(missing)
            with _VECTOR_CACHE_LOCK:
                for t, vec in zip(missing, computed, strict=True):
                    results[t] = vec
                    _VECTOR_CACHE[t] = vec
                while len(_VECTOR_CACHE) > _VECTOR_CACHE_MAX:
                    _VECTOR_CACHE.popitem(last=False)
        return [list(results[t]) for t in texts]

    return _embed
