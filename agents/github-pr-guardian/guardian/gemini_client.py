"""Gemini API client for intelligent code review and security analysis."""

from __future__ import annotations
import json
import os
import re
import ssl
import urllib.error
import urllib.request
from typing import Any


def _get_ssl_context() -> ssl.SSLContext:
    """Create a verified SSL context using certifi on macOS if available."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


REVIEW_SYSTEM_PROMPT = """You are "GitHub PR Guardian", an elite open-source maintainer and security engineer.
Your mission is to perform an uncompromising, constructive, and accurate code review on the provided Pull Request git diff.

Your review must thoroughly examine:
1. SECURITY & VULNERABILITIES:
   - Secret/credential leakage (API tokens, passwords, private keys).
   - Insecure operations: SQL injection, remote code execution (`eval`, `exec`, `os.system`), command injection.
   - Insecure deserialization, SSRF, XSS, or path traversal.

2. CODE QUALITY & BEST PRACTICES:
   - Error handling, edge cases, race conditions, memory leaks, resource cleanup.
   - Overly complex logic, missing abstractions, bad naming, dead code.
   - Type hints, documentation, and maintainability.

3. ARCHITECTURE & OPEN-SOURCE COMPLIANCE:
   - Monorepo isolation: ensure modifications don't corrupt global or unrelated configurations.
   - Dependency risks: hallucinated packages, typosquatting, unpinned versions.
   - Test and documentation adequacy: are tests or README updates missing for newly added functionality?

You must respond ONLY with a valid JSON object matching the following structure (no markdown fences, just pure JSON):
{
  "verdict": "APPROVE" | "REQUEST_CHANGES" | "COMMENT",
  "risk_score": <integer from 0 to 100, where 0 is pristine/safe and 100 is critical danger>,
  "risk_level": "LOW" | "MEDIUM" | "HIGH" | "CRITICAL",
  "executive_summary": "<concise 2-3 sentence overview of changes and overall health>",
  "key_strengths": ["<positive aspect 1>", "<positive aspect 2>"],
  "findings": [
    {
      "file": "<filepath>",
      "line": <line number if identifiable from diff or null>,
      "category": "SECURITY" | "QUALITY" | "DEPENDENCY" | "TESTING" | "COMPLIANCE",
      "severity": "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "INFO",
      "title": "<short descriptive title>",
      "comment": "<actionable and specific feedback>",
      "suggested_fix": "<concrete code replacement or remediation step>"
    }
  ],
  "test_coverage_recommendations": [
    "<recommendation on test cases that should be added>"
  ],
  "maintainer_notes": "<strategic advice for the maintainer reviewing this PR>"
}
"""


class GeminiClient:
    """Client for Google Gemini API."""

    def __init__(self, api_key: str | None = None, model: str = "gemini-2.5-flash"):
        self.api_key = (api_key or os.getenv("GEMINI_API_KEY", "")).strip()
        self.model = os.getenv("GEMINI_MODEL", model).strip()

    def analyze_diff(
        self,
        diff_text: str,
        pr_title: str = "",
        pr_description: str = "",
        static_findings_summary: str = "",
    ) -> dict[str, Any]:
        """Analyze a diff with Gemini and return structured review dictionary."""
        if not self.api_key:
            raise ValueError(
                "Gemini API key is missing. Set GEMINI_API_KEY in your environment or .env file."
            )

        # Truncate extremely large diffs if needed to stay within token limits
        max_diff_len = 100_000
        truncated_diff = diff_text[:max_diff_len]
        if len(diff_text) > max_diff_len:
            truncated_diff += "\n\n[...diff truncated for model review context...]"

        user_content = f"""Please review this Pull Request:

PR Title: {pr_title or 'N/A'}
PR Description:
{pr_description or 'No description provided.'}

Static Heuristics Pre-Scan Alerts:
{static_findings_summary or 'No static alerts detected.'}

Git Diff:
```diff
{truncated_diff}
```
"""

        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"

        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": user_content}],
                }
            ],
            "systemInstruction": {
                "parts": [{"text": REVIEW_SYSTEM_PROMPT}],
            },
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.2,
            },
        }

        req = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=45, context=_get_ssl_context()) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
                candidate = resp_data.get("candidates", [{}])[0]
                text_response = (
                    candidate.get("content", {})
                    .get("parts", [{}])[0]
                    .get("text", "{}")
                )
                return self._parse_json_response(text_response)
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Gemini API request failed (HTTP {e.code}): {error_body}")
        except Exception as e:
            raise RuntimeError(f"Failed to query Gemini API: {e}")

    def _parse_json_response(self, text: str) -> dict[str, Any]:
        """Extract and parse JSON safely from model response."""
        cleaned = text.strip()
        # Remove markdown code block if present
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\n", "", cleaned)
            cleaned = re.sub(r"\n```$", "", cleaned)
            cleaned = cleaned.strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            # Fallback regex search for JSON object
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if match:
                return json.loads(match.group(0))
            raise RuntimeError("Model did not return a valid JSON review response.")
