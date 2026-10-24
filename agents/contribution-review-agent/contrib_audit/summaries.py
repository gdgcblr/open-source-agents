"""Per-project summaries for triage (stretch goal).

Reads each project's README problem statement & example output and writes
at most 2 sentences: what it does, and whether the README shows a real run.
Never scores, ranks, or compares projects.
Batches requests, retries with backoff for rate limits, redacts secrets.
"""
from __future__ import annotations

import os
import re
import time
from typing import Optional

_SECRET_RE = re.compile(
    r"(AIza[0-9A-Za-z\-_]{35}"
    r"|sk-[A-Za-z0-9]{20,}"
    r"|(ghp|gho|ghs|ghr|github_pat)_[A-Za-z0-9_]{36,}"
    r"|AKIA[0-9A-Z]{16}"
    r"|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
    r"|xox[baprs]-[0-9A-Za-z\-]{10,})"
)


def _redact(text: str) -> str:
    return _SECRET_RE.sub("[REDACTED]", text)


def summarize_readmes(
    pr_readmes: dict[int, str],
    model_name: Optional[str] = None,
    max_retries: int = 3,
) -> dict[int, str]:
    """Generate concise 2-sentence summaries for projects in a PR batch.

    Args:
        pr_readmes: Map of PR number -> extracted README text (problem statement + example).
        model_name: Model name override (defaults to MODEL_NAME env or 'gemini-2.5-flash').
        max_retries: Number of retries on 429 rate limits.

    Returns:
        Map of PR number -> summary string. Empty dict if no API key is available.
    """
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        return {}

    if not pr_readmes:
        return {}

    try:
        from google import genai
        client = genai.Client(api_key=api_key)
    except Exception:
        return {}

    target_model = model_name or os.getenv("MODEL_NAME", "gemini-flash-latest")
    summaries: dict[int, str] = {}

    # Batch up to 5 PRs at a time to stay within token & rate limits
    items = list(pr_readmes.items())
    batch_size = 5

    for i in range(0, len(items), batch_size):
        chunk = items[i : i + batch_size]
        prompt_parts = [
            "You are an objective open-source assistant.",
            "For each project below, write at most 2 sentences:",
            "Sentence 1: What the project does.",
            "Sentence 2: Whether the README shows a real run output or placeholder/simulated text.",
            "STRICT RULES: Never score, rank, grade, or compare projects on quality or creativity.",
            "Format your answer as JSON mapping the PR number as a string to the 2-sentence summary string.\n",
        ]

        for pr_num, text in chunk:
            clean_text = _redact(text[:2500])
            prompt_parts.append(f"--- PR #{pr_num} ---\n{clean_text}\n")

        prompt = "\n".join(prompt_parts)

        # Retry loop for rate limits
        delay = 2.0
        for attempt in range(max_retries):
            try:
                response = client.models.generate_content(
                    model=target_model,
                    contents=prompt,
                )
                text = response.text or ""
                # Parse JSON if possible
                import json
                # Strip markdown json blocks
                clean = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE)
                data = json.loads(clean)
                for pr_num, _ in chunk:
                    if str(pr_num) in data:
                        summaries[pr_num] = data[str(pr_num)].strip()
                    elif pr_num in data:
                        summaries[pr_num] = data[pr_num].strip()
                break
            except Exception as exc:
                if attempt < max_retries - 1:
                    time.sleep(delay)
                    delay *= 2
                else:
                    # Fall back to empty summary on error
                    pass

    return summaries
