#!/usr/bin/env python3
"""
pr-reviewer: Autonomous AI agent for pull request security, quality, and performance review.

Powered by Google Agent Development Kit (ADK) and Gemini.
Inspects Git diffs (or branch comparisons) and provides structured, actionable
code review reports with security checks, performance analysis, and inline suggestions.

Usage:
    python main.py                     # Review current branch changes against 'main'
    python main.py --base origin/main  # Review against a specific base ref
    python main.py --staged            # Review only staged changes
    python main.py -o review.md        # Save review report to markdown file
"""

import argparse
import asyncio
import os
import subprocess
import sys
from typing import Dict, List, Optional

from dotenv import load_dotenv
from google.adk import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

load_dotenv()
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(SCRIPT_DIR, ".env"))

API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
if API_KEY:
    os.environ["GEMINI_API_KEY"] = API_KEY
    os.environ["GOOGLE_API_KEY"] = API_KEY

APP_NAME = "pr-reviewer"
USER_ID = "pr-reviewer-user"


# ---------------------------------------------------------------------------
# ADK Tools
# ---------------------------------------------------------------------------

def get_pr_diff(base_branch: str = "main", staged_only: bool = False, max_chars: int = 30000) -> dict:
    """
    Retrieves the code diff of the pull request.
    Can compare base against HEAD or view staged modifications.
    """
    if staged_only:
        cmd = ["git", "diff", "--staged"]
    else:
        # Check if base branch exists, fallback to HEAD~1 if not found
        check = subprocess.run(["git", "rev-parse", "--verify", base_branch], capture_output=True, text=True)
        target = f"{base_branch}...HEAD" if check.returncode == 0 else "HEAD~1"
        cmd = ["git", "diff", target]

    excludes = [
        ":(exclude)*package-lock.json",
        ":(exclude)*yarn.lock",
        ":(exclude)*poetry.lock",
        ":(exclude)*Cargo.lock",
    ]
    res = subprocess.run(cmd + excludes, capture_output=True, text=True)
    diff = res.stdout.strip()

    if not diff:
        return {"error": "no_diff_found", "diff": ""}

    if len(diff) > max_chars:
        diff = diff[:max_chars] + f"\n\n[...diff truncated: showing first {max_chars} chars of {len(diff)}.]"

    return {"error": "", "diff": diff}


def get_pr_changed_files(base_branch: str = "main", staged_only: bool = False) -> dict:
    """
    Lists changed files and their status (A/M/D) along with line diff stats.
    """
    if staged_only:
        cmd_names = ["git", "diff", "--staged", "--name-status"]
        cmd_stat = ["git", "diff", "--staged", "--stat"]
    else:
        check = subprocess.run(["git", "rev-parse", "--verify", base_branch], capture_output=True, text=True)
        target = f"{base_branch}...HEAD" if check.returncode == 0 else "HEAD~1"
        cmd_names = ["git", "diff", target, "--name-status"]
        cmd_stat = ["git", "diff", target, "--stat"]

    res_names = subprocess.run(cmd_names, capture_output=True, text=True)
    res_stat = subprocess.run(cmd_stat, capture_output=True, text=True)

    summary = f"Changed Files:\n{res_names.stdout.strip()}\n\nDiff Statistics:\n{res_stat.stdout.strip()}"
    return {"summary": summary}


def compute_blast_radius(base_branch: str = "main", staged_only: bool = False) -> dict:
    """
    Computes a quantitative Blast Radius & Risk Assessment on the pull request:
      - Line churn (insertions, deletions)
      - File count and core module sensitivity (auth, db, config, ci)
      - Calculates Risk Score (0-100) with visual meter.
    """
    target = ["--staged"] if staged_only else [f"{base_branch}...HEAD"]
    check = subprocess.run(["git", "rev-parse", "--verify", base_branch], capture_output=True, text=True)
    if not staged_only and check.returncode != 0:
        target = ["HEAD~1"]

    res_files = subprocess.run(["git", "diff"] + target + ["--name-only"], capture_output=True, text=True)
    files = [f.strip() for f in res_files.stdout.splitlines() if f.strip()]

    res_numstat = subprocess.run(["git", "diff"] + target + ["--numstat"], capture_output=True, text=True)
    additions, deletions = 0, 0
    for line in res_numstat.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            try:
                additions += int(parts[0])
                deletions += int(parts[1])
            except ValueError:
                pass

    total_churn = additions + deletions

    sensitive_domains = []
    risk_score = 10
    for f in files:
        f_lower = f.lower()
        if any(k in f_lower for k in ["auth", "security", "token", "crypto", "oauth"]):
            if "Authentication & Security" not in sensitive_domains:
                sensitive_domains.append("Authentication & Security")
                risk_score += 25
        if any(k in f_lower for k in ["db", "database", "migration", "schema", "model"]):
            if "Database & Schema" not in sensitive_domains:
                sensitive_domains.append("Database & Schema")
                risk_score += 20
        if any(k in f_lower for k in ["config", "setting", ".env", "secret"]):
            if "Configuration & Secrets" not in sensitive_domains:
                sensitive_domains.append("Configuration & Secrets")
                risk_score += 15
        if any(k in f_lower for k in ["docker", "k8s", "workflow", "ci", ".github"]):
            if "CI/CD & Infrastructure" not in sensitive_domains:
                sensitive_domains.append("CI/CD & Infrastructure")
                risk_score += 15

    if total_churn > 500:
        risk_score += 20
    elif total_churn > 200:
        risk_score += 10

    risk_score = min(100, risk_score)
    filled = int(risk_score / 10)
    meter = f"[{'█' * filled}{'░' * (10 - filled)}] {risk_score}%"

    level = "LOW"
    if risk_score >= 70:
        level = "CRITICAL / HIGH"
    elif risk_score >= 40:
        level = "MEDIUM"

    report = (
        f"### 🌐 Blast Radius & Surface Impact\n"
        f"- **File Count:** {len(files)} file(s) touched\n"
        f"- **Code Churn:** +{additions} / -{deletions} ({total_churn} lines modified)\n"
        f"- **Critical Surfaces:** {', '.join(sensitive_domains) if sensitive_domains else 'None (standard application logic)'}\n"
        f"- **Risk Level:** **{level}** `{meter}`\n"
    )

    return {
        "file_count": len(files),
        "additions": additions,
        "deletions": deletions,
        "total_churn": total_churn,
        "sensitive_domains": sensitive_domains,
        "risk_score": risk_score,
        "risk_level": level,
        "report_markdown": report,
    }


def read_repo_file(file_path: str, max_lines: int = 300) -> dict:
    """
    Reads a full file from the repository to give the agent surrounding context
    beyond the raw diff snippet.
    """
    clean_path = os.path.normpath(file_path)
    if not os.path.exists(clean_path):
        return {"error": f"File '{file_path}' does not exist.", "content": ""}

    try:
        with open(clean_path, "r", encoding="utf-8", errors="replace") as f:
            lines = [f.readline() for _ in range(max_lines)]
            content = "".join(lines)
            if len(lines) == max_lines:
                content += "\n[...file truncated after 300 lines]"
            return {"error": "", "content": content}
    except Exception as e:
        return {"error": str(e), "content": ""}


# ---------------------------------------------------------------------------
# Agent Definition & Review Instructions
# ---------------------------------------------------------------------------

INSTRUCTION = """
You are a Principal Software Engineer and Staff Security Architect conducting a Pull Request review.
Your goal is to provide a constructive, thorough, and highly actionable code review.

## Review Pillars
1. **Security & Privacy (Highest Priority)**:
   - Identify OWASP Top 10 vulnerabilities (SQLi, XSS, SSRF, command injection, path traversal).
   - Flag hardcoded secrets, API keys, credentials, or unprotected sensitive endpoints.
2. **Performance & Complexity**:
   - Detect N+1 queries, unindexed lookups, redundant loop allocations, and blocking I/O.
   - Note algorithmic complexity issues or memory leaks.
3. **Correctness & Reliability**:
   - Spot unhandled null/undefined values, uncaught exceptions, race conditions, or off-by-one errors.
   - Verify proper error handling and resource cleanup (context managers, closing sockets/files).
4. **Code Quality & Maintainability**:
   - Check API consistency, readability, modularity, and adherence to language idioms.
   - Check if unit tests or documentation are needed for new functionality.

## Output Structure
Your response must be formatted in clean GitHub Flavored Markdown:

# PR Code Review Report

### 🎯 Summary of Changes
- 2-3 sentences explaining what the PR accomplishes and its scope.

### 🛡️ Security & Quality Findings
Use a table or bulleted list categorized by severity:
- **[CRITICAL]** / **[WARNING]** / **[SUGGESTION]** / **[NOTE]**
- Include file name, line context, explanation of the issue, and concrete before/after fix.

### 💡 Positive Highlights
- Call out good design choices, clean refactors, or solid test coverage.

### 🏁 Final Recommendation
One of:
- **APPROVE**: Safe and clean to merge.
- **COMMENT**: Good changes, minor non-blocking suggestions.
- **REQUEST_CHANGES**: Blocking security flaws or regressions must be fixed before merging.
"""


def run_pr_reviewer(base_branch: str, staged_only: bool, model_name: str) -> str:
    """Runs the ADK PR review agent with quantitative Blast Radius metrics."""
    blast_radius = compute_blast_radius(base_branch, staged_only)

    agent = Agent(
        name="pr_reviewer",
        model=model_name,
        description="Autonomous Pull Request review agent for security and code quality.",
        instruction=INSTRUCTION,
        tools=[get_pr_changed_files, get_pr_diff, read_repo_file],
    )

    session_service = InMemorySessionService()
    session = asyncio.run(session_service.create_session(app_name=APP_NAME, user_id=USER_ID))

    runner = Runner(
        agent=agent,
        app_name=APP_NAME,
        session_service=session_service,
    )

    prompt = (
        f"Perform a comprehensive code review on the pull request changes.\n"
        f"Base reference: '{base_branch}', Staged only: {staged_only}.\n"
        f"Computed Blast Radius: {blast_radius['file_count']} files, {blast_radius['total_churn']} lines churn, Risk: {blast_radius['risk_level']}.\n"
        f"1. First call get_pr_changed_files to see what touched.\n"
        f"2. Then call get_pr_diff to inspect the actual changes.\n"
        f"3. If needed, call read_repo_file on specific files for broader context.\n"
        f"4. Synthesize your final review report."
    )

    message = types.Content(role="user", parts=[types.Part(text=prompt)])

    collected_text = []
    for event in runner.run(user_id=USER_ID, session_id=session.id, new_message=message):
        if event.is_final_response() and event.content and event.content.parts:
            for part in event.content.parts:
                if getattr(part, "text", None):
                    collected_text.append(part.text)

    review_body = "".join(collected_text).strip()
    return f"{blast_radius['report_markdown']}\n{review_body}"


def main():
    parser = argparse.ArgumentParser(
        description="Autonomous AI agent for PR code review and security audits."
    )
    parser.add_argument("--base", type=str, default="main", help="Base branch/ref to compare against (default: 'main').")
    parser.add_argument("--staged", action="store_true", help="Review only currently staged Git changes.")
    parser.add_argument("--model", type=str, default=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"), help="Gemini model.")
    parser.add_argument("--output", "-o", type=str, default=None, help="Save review report to a file.")

    args = parser.parse_args()

    if not (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")):
        print("Error: GEMINI_API_KEY or GOOGLE_API_KEY is not set.", file=sys.stderr)
        print("Set it in your environment or create a .env file:")
        print(f"  cp {os.path.join(SCRIPT_DIR, '.env.example')} {os.path.join(SCRIPT_DIR, '.env')}")
        sys.exit(1)

    print(f"Running PR Review Agent with {args.model}...", file=sys.stderr)
    report = run_pr_reviewer(args.base, args.staged, args.model)

    if not report:
        print("Agent did not return a review report.", file=sys.stderr)
        sys.exit(1)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(report + "\n")
        print(f"✓ PR review saved to {args.output}")
    else:
        print(report)


if __name__ == "__main__":
    main()
