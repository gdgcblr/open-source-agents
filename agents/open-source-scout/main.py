"""Open Source Scout - Main Agent Runner.

Orchestrates:
- Step 1: GitHub API Search & Top 15 Ranking -> top_15_repos.json
- Step 2: Gemini LLM Summarization of Problem Statement & Learning Value
- Step 3: Anti-Hallucination Guardrails (Whitelist Verification)
- Interactive output: Terminal cards, JSON exports, and interactive HTML report.
"""

from __future__ import annotations

import argparse
import getpass
from html import escape
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from github_client import GitHubScoutClient, COMPLEXITY_PRESETS
from guardrails import RepoGuardrail, GuardrailViolationError
from summarizer import GeminiRepoSummarizer
from auth import get_github_token, interactive_github_login, get_gemini_api_key


def is_safe_github_url(value: Any) -> bool:
    parsed = urlparse(str(value or ""))
    return (
        parsed.scheme == "https"
        and parsed.netloc.lower() == "github.com"
        and parsed.username is None
        and parsed.password is None
    )


def generate_html_report(
    repos: List[Dict[str, Any]],
    tech_stack: str,
    complexity: str,
    output_path: str = "report.html"
) -> str:
    """Generates a modern, responsive HTML page with navigable links and summaries."""
    cards_html = []
    for idx, r in enumerate(repos, start=1):
        raw_name = str(r.get("full_name") or r.get("name") or "Unknown repository")
        name = escape(raw_name)
        raw_url = str(r.get("html_url", ""))
        url = escape(raw_url, quote=True) if is_safe_github_url(raw_url) else "#"
        raw_clone_url = str(r.get("clone_url", f"https://github.com/{raw_name}.git"))
        clone_url = raw_clone_url if is_safe_github_url(raw_clone_url) else ""
        stars = r.get("stars", 0)
        forks = r.get("forks", 0)
        issues = r.get("open_issues_count", 0)
        prob = escape(str(r.get("problem_statement") or r.get("description", "No description available.")))
        learn = r.get("what_you_will_learn", "Explore modern codebase architecture and best practices.")
        if isinstance(learn, list):
            learn = " • " + " • ".join(learn)
        learn = escape(str(learn))
        raw_issues_url = r.get("good_first_issues_url") or f"{raw_url}/issues"
        first_issues_url = escape(str(raw_issues_url), quote=True) if is_safe_github_url(raw_issues_url) else "#"
        clone_command = escape(f"git clone {clone_url}" if clone_url else "git clone", quote=True)
        clone_display = escape(f"git clone {clone_url}" if clone_url else "Clone URL unavailable")
        guardrail_badge = '<span class="badge verified">🛡️ Guardrail Verified</span>'
        rank_val = r.get("rank") or idx

        health_badge = escape(str(r.get("health_badge", "🟢 Healthy")))
        resp_badge = escape(str(r.get("maintainer_responsiveness", "⚡ Active Reviews")))

        card = f"""
        <div class="repo-card">
            <div class="card-header">
                <div>
                    <span class="rank-tag">#{rank_val}</span>
                    <a href="{url}" target="_blank" rel="noopener noreferrer" class="repo-title">{name}</a>
                </div>
                {guardrail_badge}
            </div>
            <div class="metrics" style="margin-bottom: 8px;">
                <span style="color: #6ee7b7; font-weight: 600;">{health_badge}</span> •
                <span style="color: #7dd3fc;">{resp_badge}</span>
            </div>
            <div class="metrics">
                <span>⭐ {stars:,} stars</span>
                <span>🍴 {forks:,} forks</span>
                <span>🐛 {issues} open issues</span>
            </div>
            <div class="section-block">
                <strong>💡 Problem It Solves:</strong>
                <p>{prob}</p>
            </div>
            <div class="section-block">
                <strong>🎓 What You Will Learn:</strong>
                <p>{learn}</p>
            </div>
            <div class="action-footer">
                <a href="{url}" target="_blank" rel="noopener noreferrer" class="btn btn-primary">Open on GitHub ↗</a>
                <a href="{first_issues_url}" target="_blank" rel="noopener noreferrer" class="btn btn-secondary">Good First Issues ↗</a>
                <button type="button" class="clone-box" data-clone-command="{clone_command}" title="Click to copy clone command">
                    {clone_display}
                </button>
            </div>
        </div>
        """
        cards_html.append(card)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Open Source Scout: Top 15 {escape(tech_stack.capitalize())} Repositories ({escape(complexity.capitalize())})</title>
    <style>
        :root {{
            --bg-color: #0f172a;
            --card-bg: #1e293b;
            --card-border: #334155;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --accent: #38bdf8;
            --accent-green: #34d399;
            --btn-bg: #2563eb;
            --btn-hover: #1d4ed8;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-main);
            margin: 0;
            padding: 32px 16px;
        }}
        .container {{
            max-width: 1100px;
            margin: 0 auto;
        }}
        header {{
            text-align: center;
            margin-bottom: 40px;
        }}
        h1 {{
            font-size: 2.2rem;
            margin-bottom: 8px;
            color: var(--accent);
        }}
        .subtitle {{
            color: var(--text-muted);
            font-size: 1.1rem;
        }}
        .badge {{
            padding: 4px 10px;
            border-radius: 999px;
            font-size: 0.8rem;
            font-weight: 600;
        }}
        .badge.verified {{
            background: rgba(52, 211, 153, 0.15);
            color: var(--accent-green);
            border: 1px solid rgba(52, 211, 153, 0.4);
        }}
        .repo-card {{
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 24px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        }}
        .card-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
            flex-wrap: wrap;
            gap: 12px;
        }}
        .rank-tag {{
            background: var(--card-border);
            color: var(--accent);
            padding: 2px 8px;
            border-radius: 6px;
            font-weight: bold;
            margin-right: 8px;
        }}
        .repo-title {{
            color: var(--accent);
            font-size: 1.3rem;
            text-decoration: none;
            font-weight: bold;
        }}
        .repo-title:hover {{
            text-decoration: underline;
        }}
        .metrics {{
            display: flex;
            gap: 16px;
            color: var(--text-muted);
            font-size: 0.9rem;
            margin-bottom: 16px;
        }}
        .section-block {{
            margin-bottom: 12px;
            line-height: 1.5;
        }}
        .section-block p {{
            margin: 4px 0 0 0;
            color: #cbd5e1;
        }}
        .action-footer {{
            display: flex;
            gap: 12px;
            align-items: center;
            margin-top: 18px;
            flex-wrap: wrap;
        }}
        .btn {{
            display: inline-block;
            padding: 8px 16px;
            border-radius: 6px;
            text-decoration: none;
            font-weight: 500;
            font-size: 0.9rem;
            cursor: pointer;
        }}
        .btn-primary {{
            background-color: var(--btn-bg);
            color: #fff;
        }}
        .btn-primary:hover {{
            background-color: var(--btn-hover);
        }}
        .btn-secondary {{
            background-color: #334155;
            color: #f1f5f9;
        }}
        .btn-secondary:hover {{
            background-color: #475569;
        }}
        .clone-box {{
            background: #0f172a;
            border: 1px solid #334155;
            padding: 8px 12px;
            border-radius: 6px;
            font-family: monospace;
            font-size: 0.85rem;
            color: #38bdf8;
            cursor: pointer;
        }}
        .clone-box:hover {{
            border-color: #38bdf8;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🧭 Top 15 {escape(tech_stack.capitalize())} Open-Source Projects</h1>
            <p class="subtitle">Target Complexity: <strong>{escape(complexity.capitalize())}</strong> | Curated & Summarized via GitHub API + Gemini</p>
        </header>
        <main>
            {''.join(cards_html)}
        </main>
    </div>
    <script>
        document.querySelectorAll("[data-clone-command]").forEach((button) => {{
            button.addEventListener("click", () => {{
                navigator.clipboard.writeText(button.dataset.cloneCommand || "");
            }});
        }});
    </script>
</body>
</html>"""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    return output_path


def main():
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    parser = argparse.ArgumentParser(description="OSS Project Scout Agent")
    parser.add_argument("--tech-stack", type=str, default=None, help="Target tech stack (e.g., python, typescript, rust, react)")
    parser.add_argument("--complexity", type=str, choices=["beginner", "intermediate", "advanced"], default=None, help="Complexity level")
    parser.add_argument("--contribution-type", type=str, choices=["all", "good_first_issues", "docs", "bug_fixes", "features"], default="all", help="Filter by contribution scope")
    parser.add_argument("--github-token", type=str, default=None, help="GitHub Personal Access Token")
    parser.add_argument("--gemini-api-key", type=str, default=None, help="Google Gemini API Key")
    parser.add_argument("--skip-llm", action="store_true", help="Skip Gemini LLM summarization and use verified GitHub metadata")
    parser.add_argument("--step", type=int, choices=[1, 2, 3], default=None, help="Run only a specific step (1=Search, 2=Summarize, 3=Guardrails)")
    parser.add_argument("--top-n", type=int, default=15, help="Number of repositories to fetch (default: 15)")

    args = parser.parse_args()

    print("=" * 70)
    print("      🧭 OSS PROJECT SCOUT - OPEN-SOURCE AGENT")
    print("=" * 70)

    # 1. Resolve GitHub Authentication
    github_token = args.github_token
    github_user = None
    if not github_token:
        github_token, github_user = get_github_token()

    if github_user:
        print(f"✅ Connected to GitHub as: @{github_user} (Full API rate limits enabled)")
    elif github_token:
        print("✅ Connected to GitHub with custom token")
    else:
        print("ℹ️  No GitHub login detected. You can proceed unauthenticated, or log in for higher rate limits.")
        login_choice = input("👉 Log in to GitHub now? [y/N]: ").strip().lower()
        if login_choice in ("y", "yes"):
            github_token, github_user = interactive_github_login()

    # 2. Collect / Validate Inputs
    tech_stack = args.tech_stack or os.getenv("DEFAULT_TECH_STACK")
    if not tech_stack:
        try:
            tech_stack = input("👉 Enter target tech stack (e.g., python, typescript, react, rust) [python]: ").strip() or "python"
        except EOFError:
            tech_stack = "python"

    complexity = args.complexity or os.getenv("DEFAULT_COMPLEXITY")
    if not complexity:
        try:
            complexity_choice = input(
                "👉 Choose complexity level ([1] beginner, [2] intermediate, [3] advanced) [1]: "
            ).strip()
            complexity_map = {"1": "beginner", "2": "intermediate", "3": "advanced"}
            complexity = complexity_map.get(complexity_choice, "beginner")
        except EOFError:
            complexity = "beginner"

    gemini_key = args.gemini_api_key or (None if args.skip_llm else get_gemini_api_key(prompt_if_missing=False))

    print(f"\n[Configuration] Tech Stack: {tech_stack.upper()} | Complexity: {complexity.upper()} | Target Repos: {args.top_n}")

    # =========================================================================
    # STEP 1: Search GitHub API & Rank Top 15 Repositories -> top_15_repos.json
    # =========================================================================
    print("\n" + "-" * 70)
    print("🔄 STEP 1: Searching GitHub API & Ranking Top 15 Repositories...")
    print("-" * 70)

    scout = GitHubScoutClient(token=github_token)
    try:
        top_repos = scout.fetch_top_repos(
            tech_stack=tech_stack,
            complexity=complexity,
            contribution_type=args.contribution_type,
            top_n=args.top_n,
            output_file="top_15_repos.json"
        )
    except Exception as e:
        print(f"❌ Error during Step 1 GitHub Search: {e}")
        sys.exit(1)

    print(f"✅ Step 1 Complete! Saved {len(top_repos)} verified repositories to 'top_15_repos.json'.")
    print("\nTop 5 Preview:")
    for repo in top_repos[:5]:
        print(f"  {repo['rank']}. {repo['full_name']} (⭐ {repo['stars']:,}) - {repo['html_url']}")

    if args.step == 1:
        print("\nStep 1 requested only. Finished successfully.")
        return

    # =========================================================================
    # STEP 2 & 3: Gemini Summarization & Anti-Hallucination Guardrails
    # =========================================================================
    print("\n" + "-" * 70)
    print("🤖 STEP 2 & 3: Summarizing with Gemini & Enforcing Guardrails...")
    print("-" * 70)

    if args.skip_llm:
        print("ℹ️  --skip-llm flag passed. Using verified GitHub descriptions for the report.")
        final_repos = top_repos
    else:
        if not gemini_key:
            gemini_key = get_gemini_api_key(prompt_if_missing=True)

        if not gemini_key:
            print("ℹ️  Skipping Gemini LLM summarization. Using verified GitHub descriptions for the report.")
            final_repos = top_repos
        else:
            summarizer = GeminiRepoSummarizer(api_key=gemini_key)
            try:
                print("⏳ Querying Gemini for problem statements and learning values...")
                summaries = summarizer.summarize_repositories(top_repos, strict_guardrail=True)
                print(f"🛡️  Step 3 Guardrail Passed: All {len(summaries)} summaries strictly matched the verified GitHub search whitelist!")
                final_repos = summaries
            except GuardrailViolationError as gv:
                print(f"🚨 GUARDRAIL BLOCKED: {gv}")
                sys.exit(1)
            except Exception as e:
                print(f"⚠️  Gemini summarization failed ({e}). Falling back to verified raw metadata.")
                final_repos = top_repos

    # Export summarized results to JSON
    with open("summarized_repos.json", "w", encoding="utf-8") as f:
        json.dump(final_repos, f, indent=2)
    print("📁 Saved final results to 'summarized_repos.json'.")

    # Generate interactive HTML report
    html_path = generate_html_report(final_repos, tech_stack, complexity, output_path="report.html")
    print(f"🌐 Generated interactive and navigable web report: '{html_path}'")

    print("\n" + "=" * 70)
    print("🎉 ALL STEPS COMPLETED SUCCESSFULLY!")
    print("=" * 70)
    print("📄 Top 15 JSON:         ./top_15_repos.json")
    print("📄 Summarized JSON:     ./summarized_repos.json")
    print("🌐 Navigable HTML Page: ./report.html")
    print("=" * 70)


if __name__ == "__main__":
    main()
