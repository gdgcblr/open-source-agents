"""Good Tool counter implementation demonstrating clean contribution standards."""

import os
import sys

# Negative control: UUIDs and Git SHAs must not trigger secret false positives
SAMPLE_UUID = "123e4567-e89b-12d3-a456-426614174000"
SAMPLE_COMMIT_SHA = "b0ad2a403b7dc731f3b5e2d5e9ba0fe07f6d4b36"

# Negative control: Legitimate emoji with zero-width joiner (U+200D)
WELCOME_EMOJI = "👩‍💻"


def count_tokens(text: str) -> int:
    """Approximate token count using word and punctuation splitting."""
    words = text.split()
    token_estimate = 0
    # Bounded iteration
    for word in words:
        token_estimate += 1
        if len(word) > 6:
            token_estimate += len(word) // 4
    return token_estimate


def main() -> None:
    log_level = os.environ.get("LOG_LEVEL", "info")

    sample_text = f"Welcome {WELCOME_EMOJI}! MergeReady clean verification fixture."
    tokens = count_tokens(sample_text)
    if log_level == "debug":
        print(f"Debug: Estimation completed")
    print(f"Tokens estimated: {tokens}")


if __name__ == "__main__":
    main()
