import argparse
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

from pydantic import BaseModel, Field
from dotenv import load_dotenv

from guardrails import (
    build_actionable_remediation,
    check_contributing_compliance,
    check_duplicate_prs,
    check_zero_secrets,
    validate_manifest_files,
)

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None

load_dotenv()


class PullRequestReview(BaseModel):
    verdict: str = Field(description="APPROACH, REQUEST_CHANGES, or BLOCK")
    summary: str = Field(description="A concise 2-sentence summary of the pull request.")
    security_violations: list[str] = Field(description="List of security issues found.")
    policy_violations: list[str] = Field(description="List of documentation or manifest violations.")
    actionable_remediation: list[str] = Field(description="Step-by-step shell commands or code fixes for the contributor.")


MODEL_PROVIDER = os.getenv("MODEL_PROVIDER", "ollama").lower()
MODEL_NAME = os.getenv("MODEL_NAME", "gemma3:2b" if MODEL_PROVIDER == "ollama" else "gemini-2.5-flash")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

MOCK_DIFF = """
diff --git a/agents/demo-agent/main.py b/agents/demo-agent/main.py
index 1234567..89abcdef 100644
--- a/agents/demo-agent/main.py
+++ b/agents/demo-agent/main.py
@@ -10,3 +10,5 @@
 def run():
     print("Hello world")
+    # Added helper logic
+    API_KEY = "AIzaSyDummyKeyForTestingOnly123456789"
"""


def render_text_review(review: dict) -> str:
    verdict = review.get("verdict", "APPROACH")
    summary = review.get("summary", "No summary available.")
    security_violations = review.get("security_violations", []) or []
    policy_violations = review.get("policy_violations", []) or []
    remediation = review.get("actionable_remediation", []) or []

    lines = [
        "=" * 48,
        "MAINTAINER GUARD: PR REVIEW REPORT",
        "=" * 48,
        f"Verdict: {verdict}",
        f"Summary: {summary}",
        "",
        "Security Violations:",
    ]
    if security_violations:
        lines.extend(f"- {item}" for item in security_violations)
    else:
        lines.append("- None")

    lines.extend(["", "Policy Violations:"])
    if policy_violations:
        lines.extend(f"- {item}" for item in policy_violations)
    else:
        lines.append("- None")

    lines.extend(["", "Actionable Remediation:"])
    if remediation:
        lines.extend(f"- {item}" for item in remediation)
    else:
        lines.append("- None")

    return "\n".join(lines)


def get_git_diff(repo_root: str = ".", staged: bool = False, base: str | None = None) -> str:
    cmd = ["git", "diff"]
    if staged:
        cmd = ["git", "diff", "--cached"]
    elif base:
        cmd = ["git", "diff", base]

    try:
        result = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            print(f"Git diff failed: {result.stderr.strip() or 'unknown git error'}")
            return ""
        return result.stdout
    except FileNotFoundError:
        print("Git is not installed or not available in PATH.")
        return ""


def get_changed_files(repo_root: str = ".", staged: bool = False, base: str | None = None) -> list[str]:
    cmd = ["git", "diff", "--name-only"]
    if staged:
        cmd = ["git", "diff", "--cached", "--name-only"]
    elif base:
        cmd = ["git", "diff", "--name-only", base]

    try:
        result = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            return []
        return [line.strip() for line in result.stdout.splitlines() if line.strip()]
    except FileNotFoundError:
        return []


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Review a git diff with the Maintainer Guard.")
    parser.add_argument("--repo-root", default=".", help="Repository root to inspect. Default is the current directory.")
    parser.add_argument("--staged", action="store_true", help="Review only staged changes.")
    parser.add_argument("--base", default=None, help="Compare against a git ref such as origin/main or HEAD~1.")
    parser.add_argument("--diff-file", default=None, help="Read the diff from a text file instead of git.")
    parser.add_argument("--mock", action="store_true", help="Run the built-in mock diff for demo/testing.")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="Output format for the review result.")
    parser.add_argument("--json", action="store_true", help="Deprecated alias for --format json.")
    return parser.parse_args()


def print_json(data: dict):
    print(json.dumps(data, indent=2))


def build_exit_code(verdict: str, security_issues: list[str], policy_issues: list[str]) -> int:
    if verdict == "BLOCK" or security_issues or policy_issues:
        return 1
    return 0


def parse_review_payload(raw_text: str) -> dict:
    text = raw_text.strip()
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    fallback = {
        "verdict": "APPROACH",
        "summary": "Model output could not be parsed as structured JSON; please review the diff manually.",
        "security_violations": [],
        "policy_violations": [],
        "actionable_remediation": [
            "Review the diff manually and correct any issues before merging.",
            "If running locally, retry with a stronger model or inspect the raw LLM output."
        ],
    }

    try:
        extracted = json.loads(text[text.find('{'):text.rfind('}') + 1])
        if isinstance(extracted, dict):
            return extracted
    except Exception:
        pass

    return fallback


def call_ollama(prompt: str) -> str:
    payload = json.dumps({
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False,
        "format": "json",
    }).encode("utf-8")

    request = urllib.request.Request(
        f"{OLLAMA_BASE_URL}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=180) as response:
        body = response.read().decode("utf-8")

    data = json.loads(body)
    if isinstance(data, dict) and "response" in data:
        return data["response"]
    if isinstance(data, dict) and "content" in data:
        return data["content"]
    raise RuntimeError(f"Unexpected Ollama response: {body[:500]}")


def generate_review(prompt: str) -> str:
    if MODEL_PROVIDER == "ollama":
        return call_ollama(prompt)

    if genai is None:
        raise RuntimeError("The google-genai package is not installed. Install requirements or switch to MODEL_PROVIDER=ollama.")

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY environment variable is missing for the Gemini model provider.")

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=PullRequestReview,
            system_instruction=(
                "You are a strict, helpful, open-source repository maintainer focused on repository safety, policy compliance, "
                "and actionable fixes. Return concise but specific findings and exact remediation steps."
            ),
        ),
    )
    return response.text


def run_maintainer_guard(diff_content: str, changed_files: list[str], repo_root: str = ".", emit_json: bool = False):
    print("running deterministic pre-flight guardrails...")
    sec_issues = check_zero_secrets(diff_content)
    pol_issues = validate_manifest_files(changed_files)
    contrib_issues = check_contributing_compliance(repo_root, diff_content, changed_files)
    duplicate_issues = check_duplicate_prs(repo_root, diff_content, changed_files)
    remediation = build_actionable_remediation(sec_issues + pol_issues + contrib_issues + duplicate_issues)

    if duplicate_issues:
        result = {
            "verdict": "REQUEST_CHANGES",
            "summary": "This pull request appears to overlap with an existing open PR and should be reviewed for duplication before merge.",
            "security_violations": [],
            "policy_violations": duplicate_issues,
            "actionable_remediation": remediation,
        }
        if emit_json:
            print_json(result)
        else:
            print(render_text_review(result))
        raise SystemExit(build_exit_code(result["verdict"], [], duplicate_issues))

    if sec_issues:
        result = {
            "verdict": "BLOCK",
            "summary": "The pull request was blocked before semantic review because a hardcoded secret or risky API key was detected.",
            "security_violations": sec_issues,
            "policy_violations": pol_issues + contrib_issues,
            "actionable_remediation": remediation,
        }
        if emit_json:
            print_json(result)
        else:
            print(render_text_review(result))
        raise SystemExit(build_exit_code(result["verdict"], sec_issues, pol_issues + contrib_issues))

    if pol_issues or contrib_issues:
        result = {
            "verdict": "REQUEST_CHANGES",
            "summary": "The pull request passed the secret scan but failed repository policy checks that must be fixed before merge.",
            "security_violations": [],
            "policy_violations": pol_issues + contrib_issues,
            "actionable_remediation": remediation,
        }
        if emit_json:
            print_json(result)
        else:
            print(render_text_review(result))
        raise SystemExit(build_exit_code(result["verdict"], [], pol_issues + contrib_issues))

    print(f"invoking {MODEL_PROVIDER} model for semantic code analysis...")
    prompt = f"""
    You are an expert Autonomous Maintainer Copilot for open-source repositories.
    Enforce project-specific contribution policy from the repository's CONTRIBUTING.md file when present.
    Check the diff for:
    1) hardcoded secrets or risky tokens
    2) missing dependency lock/manifest updates
    3) repository policy violations (documentation updates, changelog requirements, breaking-change flags, branch naming patterns)
    4) maintainability and intent quality

    Return valid JSON only with this structure:
    {{
      "verdict": "APPROACH|REQUEST_CHANGES|BLOCK",
      "summary": "2 sentence summary",
      "security_violations": ["..."],
      "policy_violations": ["..."],
      "actionable_remediation": ["command or fix 1", "command or fix 2"]
    }}

    Changed Files: {changed_files}

    Git Diff:
    {diff_content}
    """

    model_output = generate_review(prompt)
    review_data = parse_review_payload(model_output)
    review_model = PullRequestReview.model_validate(review_data)
    review_payload = review_model.model_dump()

    if emit_json:
        print_json(review_payload)
        return review_payload

    print(render_text_review(review_payload))
    return review_payload


if __name__ == "__main__":
    args = parse_args()
    output_format = "json" if args.json or args.format == "json" else "text"

    if args.mock:
        try:
            run_maintainer_guard(MOCK_DIFF, ["agents/demo-agent/main.py"], repo_root=".", emit_json=output_format == "json")
        except SystemExit:
            raise
        sys.exit(0)

    if args.diff_file:
        diff_path = Path(args.diff_file)
        if not diff_path.exists():
            print(f"Diff file not found: {diff_path}")
            sys.exit(1)
        diff_content = diff_path.read_text(encoding="utf-8")
        changed_files = get_changed_files(args.repo_root, staged=args.staged, base=args.base)
        if not changed_files:
            changed_files = [str(diff_path)]
    else:
        diff_content = get_git_diff(args.repo_root, staged=args.staged, base=args.base)
        changed_files = get_changed_files(args.repo_root, staged=args.staged, base=args.base)

    if not diff_content.strip():
        print("No git diff found. Nothing to review.")
        sys.exit(0)

    print(f"Reviewing diff for {len(changed_files)} changed file(s)...")
    try:
        run_maintainer_guard(diff_content, changed_files, repo_root=args.repo_root, emit_json=output_format == "json")
    except SystemExit:
        raise
