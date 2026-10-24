"""FastEmbed ONNX embedding wrapper with custom callable override support."""

from __future__ import annotations

import threading
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastembed import TextEmbedding

EmbedFn = Callable[[Sequence[str]], list[list[float]]]

_MODEL_CACHE: dict[str, TextEmbedding] = {}
_MODEL_CACHE_LOCK = threading.Lock()


def _get_fastembed_model(model_name: str) -> TextEmbedding:
    """Return a process-cached FastEmbed TextEmbedding instance."""
    with _MODEL_CACHE_LOCK:
        if model_name not in _MODEL_CACHE:
            from fastembed import TextEmbedding

            _MODEL_CACHE[model_name] = TextEmbedding(model_name=model_name)
        return _MODEL_CACHE[model_name]


class MemShieldEmbedder:
    """Embeds text strings into normalized float vectors for pgvector storage and search.

    Defaults to `fastembed` (`BAAI/bge-small-en-v1.5`, 384 dimensions) via ONNX Runtime,
    or delegates to a user-supplied `embed_fn`.
    """

    def __init__(
        self,
        model_name: str = "BAAI/bge-small-en-v1.5",
        expected_dim: int = 384,
        embed_fn: EmbedFn | None = None,
    ) -> None:
        self.model_name = model_name
        self.expected_dim = expected_dim
        self._embed_fn = embed_fn

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed a batch of document/memory strings into float lists."""
        if not texts:
            return []
        if self._embed_fn is not None:
            vectors = [list(map(float, vec)) for vec in self._embed_fn(texts)]
        else:
            model = _get_fastembed_model(self.model_name)
            vectors = [[float(x) for x in vec.tolist()] for vec in model.embed(list(texts))]

        for vec in vectors:
            if len(vec) != self.expected_dim:
                raise ValueError(
                    f"Embedding dimension mismatch: expected {self.expected_dim}, got {len(vec)}"
                )
        return vectors

    def embed_query(self, query: str) -> list[float]:
        """Embed a single search query string into a float list."""
        vectors = self.embed_documents([query])
        return vectors[0]
