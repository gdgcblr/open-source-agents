"""Gemini LLM Summarizer with Guardrail Enforcement.

Uses Google Gemini to analyze verified GitHub repositories,
summarize the problem each solves, outline what developers will learn,
and output navigable, shareable GitHub links with strict anti-hallucination guardrails.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional
import requests

from guardrails import RepoGuardrail, GuardrailViolationError

logger = logging.getLogger("Summarizer")


SYSTEM_PROMPT = """You are a Principal Software Architect and Open-Source Mentor.
Your task is to analyze a list of verified GitHub repositories and generate rich, insightful problem statements and contributor learning takeaways for each.

### STRICT SECURITY & INTEGRITY GUARDRAILS:
1. You MUST ONLY analyze the exact repositories provided in the input payload.
2. You are STRICTLY FORBIDDEN from recommending, suggesting, or including ANY repository or GitHub link that is not explicitly in the input payload.
3. Keep all repository full_names exactly as provided.

### REQUIRED OUTPUT FOR EACH REPOSITORY:
- "full_name": Exact owner/repo from payload.
- "problem_statement": A compelling, specific 2-3 sentence explanation of the real-world engineering problem this project solves, why existing alternatives were insufficient, and why this project matters. (NEVER use generic placeholders like 'Focused on x, y').
- "what_you_will_learn": 2-3 concrete architectural patterns, engineering concepts, or technical skills a contributor gains by exploring or contributing to this specific codebase.
- "why_it_fits_complexity": Brief explanation of why it fits the selected complexity level.
- "suggested_first_step": Practical actionable first step (e.g., clone, run unit tests, read CONTRIBUTING.md, or inspect good-first-issues).

Respond ONLY with a valid JSON array of objects adhering to these fields.
"""


class GeminiRepoSummarizer:
    """Uses Gemini REST API to summarize verified GitHub projects with anti-hallucination guardrails."""

    def __init__(self, api_key: Optional[str] = None, model_name: str = "gemini-3.5-flash-lite"):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model_name = model_name

    def summarize_repositories(
        self,
        verified_repos: List[Dict[str, Any]],
        strict_guardrail: bool = True
    ) -> List[Dict[str, Any]]:
        """Summarizes top repos using Gemini and validates output through RepoGuardrail."""
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is missing in .env")

        if not verified_repos:
            return []

        # Process in chunks of 8 to ensure detailed, high-quality responses and avoid token truncation
        chunk_size = 8
        all_summaries = []

        for i in range(0, len(verified_repos), chunk_size):
            chunk = verified_repos[i:i + chunk_size]
            payload = [
                {
                    "full_name": r["full_name"],
                    "description": r["description"],
                    "language": r["language"],
                    "stars": r["stars"],
                    "forks": r["forks"],
                    "topics": r["topics"][:6],
                    "complexity_level": r.get("complexity_level", "beginner"),
                }
                for r in chunk
            ]

            user_prompt = (
                f"{SYSTEM_PROMPT}\n\n"
                f"Analyze these {len(payload)} verified repositories:\n"
                f"{json.dumps(payload, indent=2)}\n\n"
                "Return a JSON array of summarized objects matching the instructions."
            )

            raw_text = self._call_gemini_rest(user_prompt)
            parsed = self._parse_json_response(raw_text)
            all_summaries.extend(parsed)

        # Enforce Guardrail (Step 3): Whitelist verification
        guardrail = RepoGuardrail(verified_repos)
        verified_summaries, violations = guardrail.validate_and_filter_summaries(
            all_summaries,
            strict=strict_guardrail
        )

        return verified_summaries

    def _call_gemini_rest(self, prompt: str) -> str:
        """Calls Google Gemini REST API directly with automatic model fallback."""
        candidate_models = [
            self.model_name,
            "gemini-3.5-flash-lite",
            "gemini-flash-latest",
            "gemini-2.5-flash-lite",
            "gemini-2.5-flash"
        ]

        last_error = None
        for model in candidate_models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self.api_key}"
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.2,
                    "responseMimeType": "application/json"
                }
            }

            try:
                response = requests.post(url, json=payload, timeout=25)
                if response.status_code == 200:
                    data = response.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts:
                            return parts[0].get("text", "")
                else:
                    last_error = f"HTTP {response.status_code}: {response.text[:200]}"
            except Exception as e:
                last_error = str(e)
                continue

        raise RuntimeError(f"Gemini API request failed across models: {last_error}")

    def _parse_json_response(self, text: str) -> List[Dict[str, Any]]:
        """Parses model response text into Python list of dictionaries."""
        clean_text = text.strip()
        if clean_text.startswith("```json"):
            clean_text = clean_text[7:]
        elif clean_text.startswith("```"):
            clean_text = clean_text[3:]
        if clean_text.endswith("```"):
            clean_text = clean_text[:-3]
        clean_text = clean_text.strip()

        try:
            data = json.loads(clean_text)
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                for v in data.values():
                    if isinstance(v, list):
                        return v
                return [data]
        except Exception as e:
            logger.error("Failed to parse JSON from Gemini response: %s\nRaw: %s", e, text[:200])
            raise ValueError(f"Gemini response could not be parsed as JSON: {e}")

        return []
