"""Speaking-time estimates based on words per minute.

Ported from NeuralLens-AI `lib/features/scripts/util/duration_estimator.dart`.
"""

from __future__ import annotations

from .config import DEFAULT_WPM, DURATION_TOLERANCE


def word_count(text: str) -> int:
    """Counts whitespace-separated tokens that contain a letter or digit.

    Token-based counting keeps Indic scripts correct: their vowel signs are
    combining marks, which character-class regexes treat as word breaks.
    """
    return sum(1 for token in text.split() if any(ch.isalnum() for ch in token))


def estimate_seconds(text: str, wpm: int = DEFAULT_WPM) -> int:
    """Estimated seconds to speak `text`; 0 for empty text."""
    words = word_count(text)
    if words == 0:
        return 0
    return max(1, round(words * 60 / wpm))


def target_words(seconds: int, wpm: int = DEFAULT_WPM) -> int:
    """Word budget that fits `seconds` of speech."""
    return max(1, round(seconds * wpm / 60))


def fits_target(seconds: int, target_seconds: int) -> bool:
    """True when `seconds` is within DURATION_TOLERANCE of the target."""
    return abs(seconds - target_seconds) <= target_seconds * DURATION_TOLERANCE


def say_by(texts: list[str], wpm: int = DEFAULT_WPM) -> list[int]:
    """Cumulative second mark by which each text should be finished."""
    marks: list[int] = []
    words = 0
    for text in texts:
        words += word_count(text)
        marks.append(round(words * 60 / wpm))
    return marks


def format_seconds(seconds: int) -> str:
    """`45s`, `1:05`, `12:00`."""
    if seconds < 60:
        return f"{seconds}s"
    return f"{seconds // 60}:{seconds % 60:02d}"
