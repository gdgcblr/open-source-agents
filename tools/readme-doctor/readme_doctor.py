#!/usr/bin/env python3
"""
README Doctor — AI Documentation Checker CLI
Scans a README.md file for essential sections and uses Gemini to generate
actionable improvements and a documentation quality report.
"""
from __future__ import annotations

import warnings
warnings.filterwarnings("ignore", category=FutureWarning)

import argparse
import os
import re
import sys
from pathlib import Path
try:
    from dotenv import load_dotenv
except ImportError:  # Offline mode can run with only the Python standard library.
    load_dotenv = None

# Essential documentation sections and common heading keywords
REQUIRED_SECTIONS = {
    "Prerequisites": [r"prerequisite", r"requirement", r"before you begin", r"dependencies"],
    "Installation": [r"install", r"setup", r"getting started", r"quick start", r"build"],
    "Configuration": [r"config", r"environment", r"\.env", r"api key", r"settings"],
    "Usage": [r"usage", r"how to run", r"example", r"running", r"commands", r"cli"],
    "Troubleshooting": [r"troubleshoot", r"faq", r"limitation", r"known issue", r"common error", r"debug"],
}


def analyze_structure(content: str) -> dict:
    """Performs deterministic checks on the README content."""
    headings = re.findall(r"^(#{1,6})\s+(.+)$", content, flags=re.MULTILINE)
    found_sections = {}
    for section, patterns in REQUIRED_SECTIONS.items():
        found_sections[section] = any(
            re.search(pattern, heading.lower()) for _, heading in headings for pattern in patterns
        )

    code_blocks = len(re.findall(r"```[\s\S]*?```", content))
    word_count = len(content.split())

    # Calculate deterministic base score (out of 100)
    section_score = sum(15 for matched in found_sections.values() if matched)  # Max 75
    code_score = min(15, code_blocks * 5)  # Max 15 (at least 3 code blocks)
    length_score = 10 if word_count >= 150 else int((word_count / 150) * 10)  # Max 10

    total_score = section_score + code_score + length_score

    return {
        "sections": found_sections,
        "code_blocks": code_blocks,
        "word_count": word_count,
        "score": total_score,
    }


def generate_ai_suggestions(content: str, missing_sections: list[str]) -> str:
    """Calls the Gemini API to critique the README and draft missing sections."""
    if load_dotenv is not None:
        load_dotenv(Path(__file__).with_name(".env"))
    api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        return (
            "⚠️ GEMINI_API_KEY not found in environment. "
            "Skipping LLM analysis. Set GEMINI_API_KEY in your .env file for AI suggestions."
        )

    try:
        from google import genai
    except ImportError:
        return "⚠️ google-genai is not installed. Install requirements.txt or use --offline."

    client = genai.Client(api_key=api_key)

    prompt = f"""You are 'README Doctor', a strict but helpful technical documentation reviewer.
Analyze the following project README.md and provide a concise quality review.

Missing or weak sections detected by static scan: {', '.join(missing_sections) if missing_sections else 'None (all core sections present)'}.

Please provide your response in clean Markdown with these exact 3 sections:
### 1. Executive Summary
A 2-sentence assessment of the README's clarity and developer readiness.

### 2. Specific Actionable Improvements
3 to 5 bullet points identifying gaps, unclear instructions, or missing reproducibility steps (such as installation, prerequisites, usage examples, configuration, or troubleshooting).

### 3. Ready-to-Use Draft Snippets
Provide brief, copy-pasteable Markdown templates for the top missing or weakest sections tailored to the context of this README.

---
README CONTENT TO ANALYZE:
{content[:12000]}
"""
    model_name = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
    try:
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
        )
        return response.text or "Gemini returned an empty response."
    except Exception as exc:
        return f"❌ Error communicating with Gemini API: {exc}"


def format_report(file_path: str, stats: dict, ai_feedback: str | None) -> str:
    """Formats the final documentation quality report."""
    lines = [
        "# 🩺 README Doctor — Documentation Quality Report",
        f"**Target File:** `{file_path}`",
        f"**Documentation Health Score:** **{stats['score']} / 100**",
        f"**Word Count:** {stats['word_count']} words | **Code Blocks:** {stats['code_blocks']}",
        "",
        "## 📋 Core Section Checklist",
    ]

    for section, present in stats["sections"].items():
        status_icon = "✅ Present" if present else "❌ Missing"
        lines.append(f"- **{section}:** {status_icon}")

    if ai_feedback:
        lines.extend(["", "## 🤖 AI Documentation Review", ai_feedback])

    return "\n".join(lines)


def main():
    # Windows terminals may default to cp1252, which cannot print report emoji.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="README Doctor: Scan a README.md file and generate an AI quality report."
    )
    parser.add_argument(
        "path",
        nargs="?",
        default="README.md",
        help="Path to the README.md file or project directory (default: ./README.md)",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Optional path to save the generated Markdown report (e.g., report.md)",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Run only deterministic section checks without calling the LLM API",
    )
    parser.add_argument(
        "--fail-on-missing",
        action="store_true",
        help="Exit with status 2 when one or more required sections are missing",
    )

    args = parser.parse_args()
    target = Path(args.path)

    if target.is_dir():
        target = target / "README.md"

    if not target.exists():
        print(f"Error: Could not find '{target}'. Please provide a valid path.", file=sys.stderr)
        sys.exit(1)

    try:
        content = target.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        print(f"Error: Could not read '{target}': {exc}", file=sys.stderr)
        sys.exit(1)
    stats = analyze_structure(content)
    missing = [sec for sec, present in stats["sections"].items() if not present]

    ai_feedback = None
    if not args.offline:
        print(f"🔍 Scanning '{target}' and consulting Gemini for improvements...", file=sys.stderr)
        ai_feedback = generate_ai_suggestions(content, missing)

    report = format_report(str(target), stats, ai_feedback)
    print("\n" + report)

    if args.output:
        out_path = Path(args.output)
        try:
            out_path.write_text(report, encoding="utf-8")
        except OSError as exc:
            print(f"Error: Could not write report to '{out_path}': {exc}", file=sys.stderr)
            sys.exit(1)
        print(f"\n💾 Report saved to {out_path}", file=sys.stderr)

    if args.fail_on_missing and missing:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
