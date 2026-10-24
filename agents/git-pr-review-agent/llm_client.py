"""LLM client interface supporting Google Gemini, local Ollama (Gemma 2), and Mock mode."""

import os
import json
import re
from typing import Dict, Any, Optional, Tuple
import requests
from dotenv import load_dotenv

load_dotenv()

SYSTEM_INSTRUCTION = """You are a Principal Software Engineer and Security Reviewer conducting a strict code and Pull Request review.
Analyze the provided git diff and commit history.
You MUST output your response in valid JSON matching this schema:
{
  "pr_summary": {
    "title": "conventional commit title like feat(auth): add OAuth2 refresh token",
    "type": "feat|fix|refactor|docs|perf|chore|test",
    "summary": "2-3 sentence executive summary of the changes",
    "key_changes": ["change 1", "change 2"],
    "breaking_changes": ["breaking change if any or empty list"],
    "security_implications": ["security considerations"],
    "testing_checklist": ["verification step 1", "verification step 2"]
  },
  "issues": [
    {
      "file_path": "path/to/file.py",
      "line_number": 12,
      "severity": "CRITICAL|WARNING|SUGGESTION|INFO",
      "category": "security|bug|performance|style|maintainability",
      "title": "Short title",
      "description": "Clear explanation of the concern",
      "suggestion": "How to resolve it"
    }
  ],
  "risk_score": 15,
  "verdict": "APPROVE|REQUEST_CHANGES|COMMENT"
}
Ensure your output is pure valid JSON without markdown fences."""


class BaseLLMProvider:
    def review_diff(self, diff_text: str, stats: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError


class GeminiProvider(BaseLLMProvider):
    def __init__(self, api_key: str, model_name: str = "gemini-2.5-flash"):
        self.api_key = api_key
        self.model_name = model_name

    def review_diff(self, diff_text: str, stats: Dict[str, Any]) -> Dict[str, Any]:
        user_prompt = f"""Review the following git diff and change statistics:

Statistics:
- Files changed: {stats.get('files_changed', [])}
- Additions: {stats.get('additions', 0)}
- Deletions: {stats.get('deletions', 0)}
- Commit messages: {stats.get('commit_messages', [])}

Git Diff:
```
{diff_text[:35000]}
```

Provide your full review and generated PR description in the requested JSON format."""

        # Try google.genai (v1+ SDK) first, fall back to google.generativeai
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=self.api_key)
            response = client.models.generate_content(
                model=self.model_name,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    temperature=0.2,
                    response_mime_type="application/json"
                )
            )
            raw_text = response.text
        except Exception:
            # Fallback to google.generativeai
            import google.generativeai as legacy_genai
            legacy_genai.configure(api_key=self.api_key)
            model = legacy_genai.GenerativeModel(
                model_name=self.model_name,
                system_instruction=SYSTEM_INSTRUCTION,
                generation_config={"temperature": 0.2, "response_mime_type": "application/json"}
            )
            response = model.generate_content(user_prompt)
            raw_text = response.text

        return _clean_and_parse_json(raw_text)


class OllamaProvider(BaseLLMProvider):
    def __init__(self, base_url: str = "http://localhost:11434", model_name: str = "gemma2:2b"):
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name

    def review_diff(self, diff_text: str, stats: Dict[str, Any]) -> Dict[str, Any]:
        prompt = f"""{SYSTEM_INSTRUCTION}

Review this git diff:
Files: {stats.get('files_changed', [])}
Commit messages: {stats.get('commit_messages', [])}

Diff:
{diff_text[:12000]}

Respond ONLY in valid JSON."""

        res = requests.post(
            f"{self.base_url}/api/generate",
            json={"model": self.model_name, "prompt": prompt, "stream": False, "format": "json"},
            timeout=45
        )
        res.raise_for_status()
        data = res.json()
        raw_text = data.get("response", "{}")
        return _clean_and_parse_json(raw_text)


class MockProvider(BaseLLMProvider):
    """Deterministic mock provider for automated tests, offline CI, and development."""
    def __init__(self, model_name: str = "mock-agent-engine"):
        self.model_name = model_name

    def review_diff(self, diff_text: str, stats: Dict[str, Any]) -> Dict[str, Any]:
        files = stats.get("files_changed", ["repo"])
        files_str = ", ".join(files[:3]) if files else "project"
        additions = stats.get("additions", 0)
        deletions = stats.get("deletions", 0)

        issues = []
        # Add a constructive suggestion if additions are large
        if additions > 50:
            issues.append({
                "file_path": files[0] if files else "main.py",
                "line_number": 1,
                "severity": "INFO",
                "category": "maintainability",
                "title": "Comprehensive Change Set",
                "description": f"Significant updates detected (+{additions}/-{deletions}). Ensure modular decomposition.",
                "suggestion": "Verify unit tests cover all edge cases across modified modules."
            })

        return {
            "pr_summary": {
                "title": f"feat({files[0].split('/')[0] if files else 'core'}): update {files_str}",
                "type": "feat",
                "summary": f"Automated PR review generated for {len(files)} files with {additions} additions and {deletions} deletions.",
                "key_changes": [
                    f"Updated {f}" for f in files[:4]
                ] or ["Refactored internal logic"],
                "breaking_changes": [],
                "security_implications": [
                    "Static secret scan passed cleanly.",
                    "No unsanitized external inputs detected."
                ],
                "testing_checklist": [
                    "Run automated test suite: pytest",
                    "Verify clean installation in an isolated virtual environment",
                    "Check error handling under boundary inputs"
                ]
            },
            "issues": issues,
            "risk_score": 10 if additions < 100 else 25,
            "verdict": "APPROVE"
        }


def _clean_and_parse_json(raw: str) -> Dict[str, Any]:
    text = raw.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    try:
        return json.loads(text)
    except Exception as e:
        # Fallback regex extraction if model wraps json
        match = re.search(r"(\{.*\})", text, re.DOTALL)
        if match:
            return json.loads(match.group(1))
        raise ValueError(f"Failed to parse LLM response into JSON: {e}\nRaw output: {raw[:300]}")


def get_llm_provider(
    provider_type: Optional[str] = None,
    model_name: Optional[str] = None,
    api_key: Optional[str] = None
) -> Tuple[BaseLLMProvider, str]:
    """
    Factory resolving the LLM provider.
    Order of preference: Explicit -> Gemini (if key found) -> Ollama (if reachable) -> Mock.
    """
    selected_provider = (provider_type or os.getenv("LLM_PROVIDER", "")).lower()
    key = api_key or os.getenv("GEMINI_API_KEY", "")

    # Clean placeholder key
    if key in ["your_gemini_api_key_here", "AIzaSy...", ""]:
        key = None

    if selected_provider == "gemini":
        if not key:
            raise ValueError("GEMINI_API_KEY is not set. Add it to .env or use --provider mock.")
        m_name = model_name or os.getenv("MODEL_NAME", "gemini-2.5-flash")
        return GeminiProvider(api_key=key, model_name=m_name), f"Gemini ({m_name})"

    if selected_provider == "ollama":
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        m_name = model_name or "gemma2:2b"
        return OllamaProvider(base_url=base_url, model_name=m_name), f"Ollama ({m_name})"

    if selected_provider == "mock":
        return MockProvider(), "Mock Engine"

    # Auto-detection
    if key:
        m_name = model_name or os.getenv("MODEL_NAME", "gemini-2.5-flash")
        return GeminiProvider(api_key=key, model_name=m_name), f"Gemini ({m_name})"

    # Check local Ollama
    try:
        r = requests.get(f"{os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')}/api/tags", timeout=1.0)
        if r.status_code == 200:
            m_name = model_name or "gemma2:2b"
            return OllamaProvider(model_name=m_name), f"Ollama ({m_name})"
    except Exception:
        pass

    # Safe fallback
    return MockProvider(), "Mock Engine (No API key detected)"
