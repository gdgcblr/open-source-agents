REVIEW_SYSTEM_PROMPT = """You are an expert senior software engineer and security auditor conducting an automated code review on a GitHub Pull Request diff.

Your goal is to provide a constructive, thorough, and highly accurate code review report.
Focus on:
1. Identifying security vulnerabilities (injection, auth bypass, secret leaks, SSRF, memory leaks).
2. Bug detection (edge cases, unhandled nulls/exceptions, off-by-one errors).
3. Code quality, architecture, readability, and performance.
4. Actionable recommendations and suggested code diffs.

Be objective, concise, and helpful. Avoid pedantic complaints about style unless they obscure logic.
"""

def build_review_prompt(pr_title: str, diff_text: str, heuristic_issues_summary: str) -> str:
    # Truncate diff if extremely large to fit within token limits comfortably
    max_chars = 35000
    truncated_notice = ""
    if len(diff_text) > max_chars:
        diff_text = diff_text[:max_chars]
        truncated_notice = "\n\n*(Note: Diff was truncated due to length limits)*"

    return f"""Target Pull Request: {pr_title}

### Heuristic Scanner Observations:
{heuristic_issues_summary}

### Pull Request Diff:
```diff
{diff_text}
```{truncated_notice}

### Instructions:
Please generate an in-depth review in JSON format matching this schema:
{{
  "executive_summary": "2-3 paragraph summary explaining what this PR accomplishes, architectural impact, and overall stability.",
  "issues": [
    {{
      "file": "path/to/file",
      "line": 12,
      "severity": "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "INFO",
      "category": "SECURITY" | "BUG" | "CODE_SMELL" | "PERFORMANCE",
      "title": "Short title describing the problem",
      "description": "Clear explanation of the risk or bug.",
      "suggestion": "Specific code snippet or fix recommendation."
    }}
  ],
  "recommendations": [
    "Checklist item 1 for reviewer/author",
    "Checklist item 2"
  ]
}}

Output only valid JSON. Do not include markdown code fence formatting (```json) outside the JSON payload.
"""
