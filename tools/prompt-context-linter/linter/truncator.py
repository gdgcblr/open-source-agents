"""Smart Markdown and Token Budget Truncator."""

import re
from typing import Optional
from .models import TruncationPolicy, TruncationResult
from .template_linter import estimate_tokens


def balance_markdown_code_blocks(text: str) -> str:
    """Ensures code blocks are balanced with closing fences."""
    fence_count = len(re.findall(r"^```", text, re.MULTILINE))
    if fence_count % 2 != 0:
        return text.rstrip() + "\n```\n"
    return text


def truncate_context(
    text: str,
    max_tokens: Optional[int] = None,
    max_characters: Optional[int] = None,
    policy: TruncationPolicy = TruncationPolicy.SANDWICH,
    preserve_code_blocks: bool = True,
) -> TruncationResult:
    """Truncates text to fit a strict token or character budget while preserving markdown integrity.

    Args:
        text: The source prompt or document string.
        max_tokens: Maximum target tokens (approx. 4 chars per token).
        max_characters: Maximum target character count (takes precedence if given).
        policy: 'head' (keep start), 'tail' (keep end), or 'sandwich' (keep start & end).
        preserve_code_blocks: Ensure markdown code fences are properly balanced.

    Returns:
        TruncationResult with metrics and truncated text.
    """
    if max_characters is None:
        if max_tokens is not None:
            max_characters = int(max_tokens * 3.8)
        else:
            max_characters = len(text)

    original_chars = len(text)
    original_tokens = estimate_tokens(text)

    if original_chars <= max_characters:
        return TruncationResult(
            original_characters=original_chars,
            final_characters=original_chars,
            original_estimated_tokens=original_tokens,
            final_estimated_tokens=original_tokens,
            truncated=False,
            policy_used=policy,
            characters_removed=0,
            content=text,
        )

    chars_to_remove = original_chars - max_characters

    if policy == TruncationPolicy.HEAD:
        # Keep head
        cut = text[:max_characters]
        # Snap to last newline if possible
        last_nl = cut.rfind("\n")
        if last_nl > int(max_characters * 0.7):
            cut = cut[:last_nl]
        marker = f"\n\n[... Truncated {original_chars - len(cut)} characters to fit budget ...]"
        result_text = cut + marker

    elif policy == TruncationPolicy.TAIL:
        # Keep tail
        start_idx = original_chars - max_characters
        cut = text[start_idx:]
        first_nl = cut.find("\n")
        if first_nl != -1 and first_nl < int(max_characters * 0.3):
            cut = cut[first_nl + 1 :]
        marker = f"[... Truncated {original_chars - len(cut)} characters to fit budget ...]\n\n"
        result_text = marker + cut

    else:
        # Sandwich: 35% Head (System directives), 65% Tail (User query/context)
        head_len = int(max_characters * 0.35)
        tail_len = int(max_characters * 0.65)

        head_part = text[:head_len]
        last_nl = head_part.rfind("\n")
        if last_nl > int(head_len * 0.5):
            head_part = head_part[:last_nl]

        tail_part = text[original_chars - tail_len :]
        first_nl = tail_part.find("\n")
        if first_nl != -1 and first_nl < int(tail_len * 0.5):
            tail_part = tail_part[first_nl + 1 :]

        chars_cut = original_chars - (len(head_part) + len(tail_part))
        marker = f"\n\n[... Truncated {chars_cut} characters / ~{int(chars_cut / 3.8)} tokens to fit budget ...]\n\n"
        result_text = head_part + marker + tail_part

    if preserve_code_blocks:
        result_text = balance_markdown_code_blocks(result_text)

    final_chars = len(result_text)
    final_tokens = estimate_tokens(result_text)

    return TruncationResult(
        original_characters=original_chars,
        final_characters=final_chars,
        original_estimated_tokens=original_tokens,
        final_estimated_tokens=final_tokens,
        truncated=True,
        policy_used=policy,
        characters_removed=original_chars - final_chars,
        content=result_text,
    )
