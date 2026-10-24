"""
Categorizer — Uses Google Gemini to classify code components
into User Docs vs Dev Docs categories.

Classification rules sent to the LLM:
- User Docs: Public APIs, CLI commands, config options, installation, usage
- Dev Docs:  Internal architecture, private methods, class hierarchies, testing
- Both:      Setup/installation, high-level architecture overview

This module handles prompt construction, API calls, and response parsing.
"""

import json
import time
import warnings

with warnings.catch_warnings():
    warnings.simplefilter("ignore", category=FutureWarning)
    import google.generativeai as genai

from rich.console import Console

from .config import Config

console = Console()

# The system prompt that instructs Gemini how to categorize
CATEGORIZATION_SYSTEM_PROMPT = """\
You are a documentation categorizer for software projects.

Your job is to analyze a codebase structure and categorize each file into
documentation categories. You will receive a structured summary of a codebase
including file paths, classes, functions, their visibility (public/private),
docstrings, and imports.

Categorize each file into ONE of these categories:

1. "user" — User-facing documentation. This includes:
   - Public API endpoints or functions that end-users call
   - CLI entry points and command definitions
   - Configuration files that users need to modify
   - README files, setup guides, usage examples
   - Public classes/interfaces that users interact with

2. "dev" — Developer/internal documentation. This includes:
   - Internal implementation details and private modules
   - Helper/utility functions not exposed to users
   - Test files and test utilities
   - Build scripts, CI/CD configs, internal tooling
   - Architecture decisions and internal data flow

3. "both" — Belongs in both user and dev documentation:
   - Core modules that define both public API and internal logic
   - Configuration/setup that both users and developers need
   - Main entry points that explain both usage and internals

Return your response as a valid JSON object with this exact structure:
{
  "categorization": [
    {
      "path": "relative/file/path",
      "category": "user" | "dev" | "both",
      "reason": "one-line explanation of why this category was chosen",
      "doc_topics": ["list", "of", "documentation", "topics", "this file covers"]
    }
  ]
}

Rules:
- Categorize EVERY file listed in the input.
- Base your decision on the file's purpose, not just its location.
- When in doubt between "user" and "dev", choose "both".
- Return ONLY the JSON object, no additional text.
"""


def categorize_codebase(
    condensed_summary: str,
    config: Config,
) -> dict:
    """
    Send the condensed codebase summary to Gemini for categorization.

    Args:
        condensed_summary: The condensed text from analyzer.condense_for_llm().
        config: Configuration object with API key and model settings.

    Returns:
        A dict mapping file paths to their categories:
        {
            "file/path": {
                "category": "user"|"dev"|"both",
                "reason": "explanation",
                "doc_topics": ["topic1", "topic2"],
            }
        }
        Returns empty dict on failure.
    """
    genai.configure(api_key=config.gemini_api_key)
    model = genai.GenerativeModel(config.gemini_model)

    prompt = f"""{CATEGORIZATION_SYSTEM_PROMPT}

Here is the codebase structure to categorize:

{condensed_summary}
"""

    console.print("[dim]Sending codebase structure to Gemini for categorization...[/dim]")

    try:
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.1,  # Low temperature for consistent categorization
                max_output_tokens=8192,
            ),
        )
    except Exception as e:
        console.print(f"[red]Error calling Gemini API:[/red] {e}")
        return {}

    # Parse the JSON response
    raw_text = response.text.strip()
    return _parse_categorization_response(raw_text)


def _parse_categorization_response(raw_text: str) -> dict:
    """
    Parse the JSON response from Gemini into a clean dict.
    Handles cases where Gemini wraps JSON in markdown code blocks.
    """
    # Strip markdown code block fencing if present
    text = raw_text
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        console.print("[yellow]Warning:[/yellow] Could not parse Gemini response as JSON. Using fallback categorization.")
        console.print(f"[dim]Raw response (first 500 chars): {raw_text[:500]}[/dim]")
        return {}

    # Convert the list format into a dict keyed by file path
    result = {}
    categorization_list = data.get("categorization", [])

    for item in categorization_list:
        path = item.get("path", "")
        if path:
            result[path] = {
                "category": item.get("category", "both"),
                "reason": item.get("reason", ""),
                "doc_topics": item.get("doc_topics", []),
            }

    return result


def fallback_categorize(analyses: list[dict]) -> dict:
    """
    Rule-based fallback categorization when LLM is unavailable.
    Uses simple heuristics based on file path and content.

    This is used when:
    - API key is not configured
    - Gemini API call fails
    - User explicitly requests offline mode
    """
    result = {}

    for analysis in analyses:
        path = analysis["path"]
        language = analysis["language"]
        category_type = analysis["category"]

        # Default to "both"
        doc_category = "both"
        reason = "Default categorization"
        topics = []

        lower_path = path.lower()

        # Rule 1: Test files → dev only
        if ("test" in lower_path or "spec" in lower_path
                or lower_path.startswith("tests/")):
            doc_category = "dev"
            reason = "Test file"
            topics = ["testing", "test-suite"]

        # Rule 2: Config files → user (they need to know how to configure)
        elif category_type == "config":
            doc_category = "user"
            reason = "Configuration file"
            topics = ["configuration", "setup"]

        # Rule 3: Doc files → user
        elif category_type == "doc":
            doc_category = "user"
            reason = "Documentation file"
            topics = ["documentation"]

        # Rule 4: CLI entry points → user
        elif any(name in lower_path for name in ("cli", "main", "__main__", "app")):
            doc_category = "both"
            reason = "Entry point / CLI"
            topics = ["usage", "cli", "getting-started"]

        # Rule 5: Internal/private modules → dev
        elif any(part.startswith("_") for part in path.split("/")):
            doc_category = "dev"
            reason = "Internal/private module"
            topics = ["internals", "architecture"]

        # Rule 6: Files with mostly private functions → dev
        elif analysis.get("functions"):
            private_count = sum(1 for f in analysis["functions"] if f.get("is_private"))
            total = len(analysis["functions"])
            if total > 0 and private_count / total > 0.7:
                doc_category = "dev"
                reason = "Mostly private functions"
                topics = ["internals"]
            elif private_count / total < 0.3 if total > 0 else False:
                doc_category = "user"
                reason = "Mostly public functions"
                topics = ["api-reference"]

        # Rule 7: Source files default to "both"
        elif category_type == "source":
            doc_category = "both"
            reason = "Source file with mixed visibility"
            topics = ["modules"]

        result[path] = {
            "category": doc_category,
            "reason": reason,
            "doc_topics": topics,
        }

    return result
