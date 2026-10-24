"""Token counting. Uses tiktoken when installed, otherwise a labelled approximation."""

from __future__ import annotations

from functools import lru_cache
from typing import Any


@lru_cache(maxsize=1)
def _encoder() -> Any:
    try:
        import tiktoken  # optional dependency

        return tiktoken.get_encoding("o200k_base")
    except Exception:  # not installed, or encoding files unavailable offline
        return None


def count(text: str) -> tuple[int, str]:
    """Return (tokens, method). Method is 'tiktoken:o200k_base' or 'approx:chars/4'.

    tiktoken encodes for OpenAI models; for other providers it is still only an
    approximation of their tokenizer, and reports say so.
    """
    enc = _encoder()
    if enc is not None:
        return len(enc.encode(text)), "tiktoken:o200k_base"
    return (max(1, round(len(text) / 4)) if text else 0), "approx:chars/4"
