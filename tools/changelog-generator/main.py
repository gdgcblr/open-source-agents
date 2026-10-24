#!/usr/bin/env python3
"""
changelog-generator: AI-powered changelog and release notes generator.

Parses Git commit history between tags/releases, groups Conventional Commits into
structured sections (Features, Fixes, Breaking Changes, etc.), and optionally uses
Gemini to synthesize an executive release summary.

Usage:
    python main.py                  # Generate changelog for recent commits
    python main.py --from-tag v1.0  # Generate from specific tag to HEAD
    python main.py --ai             # Synthesize release highlights using Gemini
    python main.py --output CHANGELOG.md  # Write directly to file
"""

import argparse
import datetime
import os
import re
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv

load_dotenv()
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(SCRIPT_DIR, ".env"))

COMMIT_REGEX = re.compile(
    r"^(?P<type>feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)"
    r"(?:\((?P<scope>[^)]+)\))?(?P<breaking>!)?:\s*(?P<subject>.+)$",
    re.IGNORECASE,
)

SECTION_TITLES = {
    "breaking": "⚠️ Breaking Changes",
    "feat": "🚀 Features & Enhancements",
    "fix": "🐛 Bug Fixes",
    "perf": "⚡ Performance Improvements",
    "refactor": "🔨 Refactoring & Code Quality",
    "docs": "📚 Documentation Updates",
    "chore": "🧹 Maintenance & Chores",
    "other": "📦 Other Changes",
}


def get_git_tags() -> List[str]:
    """Returns sorted list of Git tags."""
    res = subprocess.run(["git", "tag", "--sort=-creatordate"], capture_output=True, text=True)
    if res.returncode == 0 and res.stdout.strip():
        return [t.strip() for t in res.stdout.splitlines() if t.strip()]
    return []


def get_commit_range(from_ref: Optional[str] = None, to_ref: str = "HEAD") -> List[Dict[str, str]]:
    """
    Retrieves commit list between two Git refs.
    Returns list of dicts with 'hash', 'author', 'date', 'subject', 'body'.
    """
    if from_ref:
        git_range = f"{from_ref}..{to_ref}"
    else:
        # If no from_ref, get all commits reachable from to_ref
        git_range = to_ref

    # Delimiter to split commit fields safely
    delimiter = "---COMMIT_DELIMITER---"
    format_str = f"%h%n%an%n%ad%n%s%n%b{delimiter}"
    res = subprocess.run(
        ["git", "log", "--date=short", f"--pretty=format:{format_str}", git_range],
        capture_output=True,
        text=True,
    )
    if res.returncode != 0:
        return []

    commits = []
    raw_blocks = res.stdout.split(delimiter)
    for block in raw_blocks:
        lines = [line for line in block.strip().splitlines()]
        if len(lines) >= 4:
            c_hash = lines[0].strip()
            c_author = lines[1].strip()
            c_date = lines[2].strip()
            c_subject = lines[3].strip()
            c_body = "\n".join(lines[4:]).strip() if len(lines) > 4 else ""
            commits.append({
                "hash": c_hash,
                "author": c_author,
                "date": c_date,
                "subject": c_subject,
                "body": c_body,
            })
    return commits


def parse_conventional_commit(commit: Dict[str, str]) -> Dict[str, Any]:
    """Parses a commit into Conventional Commit components."""
    subject = commit["subject"]
    body = commit.get("body", "")
    match = COMMIT_REGEX.match(subject)

    is_breaking = False
    if "BREAKING CHANGE:" in body or "BREAKING-CHANGE:" in body:
        is_breaking = True

    if match:
        c_type = match.group("type").lower()
        c_scope = match.group("scope")
        c_breaking = bool(match.group("breaking")) or is_breaking
        c_desc = match.group("subject").strip()
        return {
            "type": c_type,
            "scope": c_scope,
            "breaking": c_breaking,
            "description": c_desc,
            "hash": commit["hash"],
            "author": commit["author"],
            "date": commit["date"],
            "raw_subject": subject,
        }

    return {
        "type": "other",
        "scope": None,
        "breaking": is_breaking,
        "description": subject,
        "hash": commit["hash"],
        "author": commit["author"],
        "date": commit["date"],
        "raw_subject": subject,
    }


def group_commits(parsed_commits: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Groups parsed commits into categories."""
    groups: Dict[str, List[Dict[str, Any]]] = {k: [] for k in SECTION_TITLES.keys()}

    for c in parsed_commits:
        if c["breaking"]:
            groups["breaking"].append(c)
        c_type = c["type"]
        if c_type in groups:
            groups[c_type].append(c)
        else:
            groups["other"].append(c)

    return {k: v for k, v in groups.items() if v}


def generate_markdown(
    version_title: str,
    grouped: Dict[str, List[Dict[str, Any]]],
    ai_summary: Optional[str] = None,
) -> str:
    """Renders structured changelog markdown."""
    lines = [f"## {version_title} ({datetime.date.today().isoformat()})\n"]

    if ai_summary:
        lines.append("### 💡 Release Highlights")
        lines.append(ai_summary.strip() + "\n")

    for section_key, title in SECTION_TITLES.items():
        items = grouped.get(section_key, [])
        if not items:
            continue
        lines.append(f"### {title}\n")
        for item in items:
            scope_prefix = f"**{item['scope']}:** " if item.get("scope") else ""
            desc = item["description"]
            c_hash = item["hash"]
            lines.append(f"- {scope_prefix}{desc} (`{c_hash}`)")
        lines.append("")

    return "\n".join(lines).strip()


def synthesize_ai_summary(commits_text: str) -> Optional[str]:
    """Uses Gemini API to synthesize an executive release summary."""
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("Note: GEMINI_API_KEY not found. Skipping AI synthesis.", file=sys.stderr)
        return None

    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

        prompt = (
            "You are a release manager writing user-facing release notes.\n"
            "Synthesize a concise 2-4 sentence executive summary highlighting key features "
            "and bug fixes from the following git commits:\n\n"
            f"{commits_text}\n\n"
            "Write ONLY the summary paragraph. Avoid generic filler."
        )
        response = client.models.generate_content(
            model=model,
            contents=prompt,
        )
        return response.text.strip() if response.text else None
    except Exception as e:
        print(f"Warning: AI synthesis failed: {e}", file=sys.stderr)
        return None


def main():
    parser = argparse.ArgumentParser(
        description="AI-powered changelog generator from Git commit history."
    )
    parser.add_argument("--from-tag", type=str, default=None, help="Starting tag or commit reference.")
    parser.add_argument("--to-tag", type=str, default="HEAD", help="Ending tag or commit reference (default: HEAD).")
    parser.add_argument("--title", type=str, default="Unreleased", help="Version title (default: 'Unreleased').")
    parser.add_argument("--ai", action="store_true", help="Synthesize release highlights using Gemini.")
    parser.add_argument("--output", "-o", type=str, default=None, help="Write output to specified file.")
    parser.add_argument("--dry-run", action="store_true", help="Print changelog without writing to file.")

    args = parser.parse_args()

    # Auto-detect starting tag if not provided
    from_tag = args.from_tag
    if not from_tag:
        tags = get_git_tags()
        if tags:
            from_tag = tags[0]

    commits = get_commit_range(from_tag, args.to_tag)
    if not commits:
        print("No commits found in specified range.", file=sys.stderr)
        sys.exit(0)

    parsed = [parse_conventional_commit(c) for c in commits]
    grouped = group_commits(parsed)

    ai_summary = None
    if args.ai:
        commits_summary = "\n".join(f"- {c['subject']}" for c in commits)
        print("Synthesizing release highlights with Gemini...", file=sys.stderr)
        ai_summary = synthesize_ai_summary(commits_summary)

    changelog_md = generate_markdown(args.title, grouped, ai_summary)

    if args.output and not args.dry_run:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(changelog_md + "\n")
        print(f"✓ Changelog successfully written to {args.output}")
    else:
        print(changelog_md)


if __name__ == "__main__":
    main()
