"""Token counting utilities supporting BPE and fallback heuristic models."""

from typing import Optional

try:
    import tiktoken
except ImportError:
    tiktoken = None

_ENCODING_CACHE = {}


def get_encoder(encoding_name: str = "cl100k_base"):
    """Loads and caches a tiktoken encoding."""
    if tiktoken is None:
        return None
    if encoding_name not in _ENCODING_CACHE:
        try:
            _ENCODING_CACHE[encoding_name] = tiktoken.get_encoding(encoding_name)
        except Exception:
            _ENCODING_CACHE[encoding_name] = None
    return _ENCODING_CACHE[encoding_name]


def count_tokens(text: str, model_or_encoding: str = "cl100k_base") -> int:
    """Counts tokens in a string using tiktoken BPE or a deterministic heuristic fallback.

    Args:
        text: Source text string.
        model_or_encoding: Encoding identifier (e.g. 'cl100k_base', 'o200k_base') or model name.

    Returns:
        Integer token count.
    """
    if not text:
        return 0

    encoding_name = "cl100k_base"
    if "o200k" in model_or_encoding or "4o" in model_or_encoding:
        encoding_name = "o200k_base"

    encoder = get_encoder(encoding_name)
    if encoder is not None:
        try:
            return len(encoder.encode(text, disallowed_special=()))
        except Exception:
            pass

    # Heuristic fallback (~3.8 characters per token across natural language & code)
    char_len = len(text)
    word_len = len(text.split())
    # Blend characters and words for high accuracy
    heuristic = (char_len / 4.0 + word_len * 1.3) / 2.0
    return max(1, int(round(heuristic)))
