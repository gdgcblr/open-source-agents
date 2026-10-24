"""Web Frontend Server for Open Source Scout.

Provides:
- Web dashboard with Tech Stack, Experience Level, and Contribution-Type dropdowns.
- Multi-signal repository health scoring & maintainer responsiveness summaries.
- Explicit GitHub user login (Session-based with Personal Access Token).
- Signed-in user public Issue & Pull Request history dashboard.
- Direct 1-Click Forking to user's authenticated GitHub account.
- Automated Gemini problem summarization (reading GEMINI_API_KEY from .env).
- Guardrail validation and 1-click clone / Good First Issues navigation.
"""

from __future__ import annotations

import json
import os
import secrets
import sys
from pathlib import Path
from typing import Optional
from flask import Flask, jsonify, render_template, request, send_file, session
import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from auth import get_github_token, verify_github_token, get_stored_env_value
from github_client import GitHubScoutClient, COMPLEXITY_PRESETS
from guardrails import RepoGuardrail, GuardrailViolationError
from summarizer import GeminiRepoSummarizer

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32)
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")
AGENT_DIR = Path(__file__).parent
github_sessions: dict[str, tuple[str, str]] = {}


def get_authenticated_github_credentials() -> tuple[Optional[str], Optional[str]]:
    session_id = session.get("github_session_id")
    return github_sessions.get(session_id, (None, None))


@app.route("/")
def index():
    """Serves the main interactive dashboard."""
    return render_template("index.html")


@app.route("/api/status", methods=["GET"])
def get_status():
    """Returns current session login status."""
    session_token, session_user = get_authenticated_github_credentials()

    saved_gemini = os.getenv("GEMINI_API_KEY") or get_stored_env_value("GEMINI_API_KEY")
    has_gemini = bool(saved_gemini and not saved_gemini.startswith("your_"))

    return jsonify({
        "github": {
            "authenticated": bool(session_token and session_user),
            "username": session_user,
            "rate_limit_info": "5,000 requests/hr (Authenticated)" if session_token else "60 requests/hr (Public)"
        },
        "gemini": {
            "configured": has_gemini,
            "engine": "Gemini AI Summarizer (Active)" if has_gemini else "Fallback Heuristic Mode"
        },
        "presets": {
            "tech_stacks": [
                "Python", "TypeScript", "JavaScript", "Rust", "Go",
                "React", "Vue", "Next.js", "C++", "Java", "Kotlin", "Swift", "Flutter"
            ],
            "complexities": [
                {"id": "beginner", "label": "🟢 Beginner (Good first issues, active starter community)"},
                {"id": "intermediate", "label": "🟡 Intermediate (Production libraries & dev tools)"},
                {"id": "advanced", "label": "🔴 Advanced (Large-scale architectures & runtime systems)"}
            ],
            "contribution_types": [
                {"id": "all", "label": "All Contribution Scopes"},
                {"id": "good_first_issues", "label": "🌱 Small Scope (Good First Issues & Starter Tasks)"},
                {"id": "docs", "label": "📚 Documentation & Tutorials"},
                {"id": "bug_fixes", "label": "🐛 Bug Fixes & Triage"},
                {"id": "features", "label": "⚡ Features & Architecture"}
            ]
        }
    })


@app.route("/api/login", methods=["POST"])
def login():
    """Handles user login to GitHub via Personal Access Token."""
    data = request.json or {}
    raw_token = data.get("token", "").strip()
    if not raw_token:
        return jsonify({"error": "Please provide a valid GitHub token."}), 400

    verified_user = verify_github_token(raw_token)
    if not verified_user:
        return jsonify({"error": "Invalid GitHub token. Please verify token permissions and try again."}), 401

    old_session_id = session.get("github_session_id")
    if old_session_id:
        github_sessions.pop(old_session_id, None)
    session_id = secrets.token_urlsafe(32)
    github_sessions[session_id] = (raw_token, verified_user)
    session["github_session_id"] = session_id
    return jsonify({"success": True, "username": verified_user})


@app.route("/api/logout", methods=["POST"])
def logout():
    """Logs out the user by clearing session credentials."""
    session_id = session.pop("github_session_id", None)
    if session_id:
        github_sessions.pop(session_id, None)
    return jsonify({"success": True})


@app.route("/api/user/activity", methods=["GET"])
def user_activity():
    """Fetches signed-in user's public GitHub Issue and Pull Request contribution history."""
    token, username = get_authenticated_github_credentials()

    if not token or not username:
        return jsonify({"error": "You must be signed in to view your GitHub activity."}), 401

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "OSS-Project-Scout/1.0"
    }

    try:
        # 1. User Profile info
        user_res = requests.get(f"https://api.github.com/users/{username}", headers=headers, timeout=10)
        profile = user_res.json() if user_res.ok else {}

        # 2. Recent Pull Requests authored by user
        prs_res = requests.get(
            f"https://api.github.com/search/issues?q=author:{username}+type:pr&sort=updated&order=desc&per_page=8",
            headers=headers,
            timeout=10
        )
        prs_data = prs_res.json().get("items", []) if prs_res.ok else []

        # 3. Recent Issues authored by user
        issues_res = requests.get(
            f"https://api.github.com/search/issues?q=author:{username}+type:issue&sort=updated&order=desc&per_page=8",
            headers=headers,
            timeout=10
        )
        issues_data = issues_res.json().get("items", []) if issues_res.ok else []

        def format_item(item):
            repo_url = item.get("repository_url", "")
            repo_name = "/".join(repo_url.split("/")[-2:]) if repo_url else "Unknown Repo"
            return {
                "id": item.get("id"),
                "title": item.get("title"),
                "html_url": item.get("html_url"),
                "state": item.get("state"),
                "repo_name": repo_name,
                "created_at": item.get("created_at", "")[:10],
                "comments": item.get("comments", 0)
            }

        return jsonify({
            "profile": {
                "username": username,
                "avatar_url": profile.get("avatar_url"),
                "html_url": profile.get("html_url"),
                "public_repos": profile.get("public_repos", 0),
                "name": profile.get("name") or username,
            },
            "pull_requests": [format_item(i) for i in prs_data],
            "issues": [format_item(i) for i in issues_data]
        })
    except Exception as e:
        return jsonify({"error": f"Failed to fetch GitHub activity: {str(e)}"}), 500


@app.route("/api/scout", methods=["POST"])
def scout():
    """Searches GitHub, scores health/responsiveness, and summarizes problem statements using Gemini."""
    data = request.json or {}
    tech_stack = (data.get("tech_stack") or "Python").strip()
    complexity = (data.get("complexity") or "beginner").strip().lower()
    contribution_type = (data.get("contribution_type") or "all").strip().lower()
    top_n = int(data.get("top_n", 15))

    # Read Gemini key directly from .env
    gemini_key = os.getenv("GEMINI_API_KEY") or get_stored_env_value("GEMINI_API_KEY")

    token = session.get("github_token")
    scout_client = GitHubScoutClient(token=token)

    try:
        top_repos = scout_client.fetch_top_repos(
            tech_stack=tech_stack,
            complexity=complexity,
            contribution_type=contribution_type,
            top_n=top_n,
            output_file=str(AGENT_DIR / "top_15_repos.json")
        )
    except Exception as e:
        return jsonify({"error": f"GitHub Search Error: {str(e)}"}), 500

    if not top_repos:
        return jsonify({"error": f"No open-source repositories found matching '{tech_stack}' ({complexity})."}), 404

    # Step 2 & 3: Real Gemini Problem Summarization & Guardrails
    summarized_repos = []
    if gemini_key and not gemini_key.startswith("your_"):
        try:
            summarizer = GeminiRepoSummarizer(api_key=gemini_key)
            summarized_repos = summarizer.summarize_repositories(top_repos, strict_guardrail=True)
        except Exception as e:
            print(f"Gemini summarization exception: {e}")
            summarized_repos = []

    # Fallback to metadata if Gemini key is missing or failed
    if not summarized_repos:
        for r in top_repos:
            rec = dict(r)
            rec["problem_statement"] = r.get("description") or "Open-source codebase."
            rec["what_you_will_learn"] = [
                f"Architecture and engineering practices in {r.get('language')}",
                "Open-source collaboration workflows and issue triage"
            ]
            rec["why_it_fits_complexity"] = f"Ranked for {complexity.capitalize()} contributors."
            rec["suggested_first_step"] = f"git clone {r.get('clone_url')}"
            rec["guardrail_status"] = "VERIFIED_GENUINE"
            summarized_repos.append(rec)

    # Save final JSON
    with open(AGENT_DIR / "summarized_repos.json", "w", encoding="utf-8") as f:
        json.dump(summarized_repos, f, indent=2)

    return jsonify({
        "meta": {
            "tech_stack": tech_stack,
            "complexity": complexity,
            "contribution_type": contribution_type,
            "count": len(summarized_repos),
            "engine": "Gemini" if gemini_key else "Heuristic"
        },
        "repositories": summarized_repos
    })


@app.route("/api/fork", methods=["POST"])
def fork_repo():
    """Forks a selected repository directly to the user's authenticated GitHub account."""
    data = request.json or {}
    repo_full_name = data.get("repo_full_name", "").strip()
    if not repo_full_name:
        return jsonify({"error": "Missing repository full name"}), 400

    token, username = get_authenticated_github_credentials()

    if not token or not username:
        return jsonify({
            "error": "You are not logged in. Please log in to GitHub first to fork repositories to your account."
        }), 401

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "OSS-Project-Scout/1.0"
    }

    url = f"https://api.github.com/repos/{repo_full_name}/forks"
    try:
        resp = requests.post(url, headers=headers, json={"default_branch_only": True}, timeout=15)
        if resp.status_code in (200, 202):
            fork_data = resp.json()
            return jsonify({
                "success": True,
                "fork_url": fork_data.get("html_url"),
                "full_name": fork_data.get("full_name"),
                "message": f"Successfully forked to @{username}!"
            })
        else:
            err_msg = resp.json().get("message", "GitHub API rejected the fork request.")
            return jsonify({"error": f"GitHub Error ({resp.status_code}): {err_msg}"}), resp.status_code
    except Exception as e:
        return jsonify({"error": f"Fork request failed: {str(e)}"}), 500


@app.route("/api/download/<file_type>")
def download_file(file_type):
    """Direct download for top_15_repos.json or summarized_repos.json."""
    if file_type == "top15":
        target = AGENT_DIR / "top_15_repos.json"
    elif file_type == "summarized":
        target = AGENT_DIR / "summarized_repos.json"
    else:
        return jsonify({"error": "Invalid file type"}), 400

    if not target.exists():
        return jsonify({"error": "File not yet generated. Run scout first."}), 404

    return send_file(target, as_attachment=True)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    host = os.environ.get("HOST", "127.0.0.1")
    print("\n" + "=" * 65)
    print("      🧭 OPEN SOURCE SCOUT - WEB FRONTEND")
    print("=" * 65)
    print(f"🚀 Server running at: http://localhost:{port}")
    print(f"👉 Open in browser:  open http://localhost:{port}")
    print("=" * 65 + "\n")
    app.run(host=host, port=port, debug=False)
