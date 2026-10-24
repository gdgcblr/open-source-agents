"""Authentication & Configuration Assistant for GitHub and Gemini API.

Provides seamless login for GitHub:
1. Auto-detects GitHub CLI (`gh auth token`) for 1-click zero-token login.
2. Supports `.env` and environment variables.
3. Offers browser-assisted login if no credentials exist.
Also manages the Gemini API key onboarding seamlessly.
"""

from __future__ import annotations

import getpass
import os
import shutil
import subprocess
import webbrowser
from pathlib import Path
from typing import Optional, Tuple
import requests


ENV_PATH = Path(__file__).parent / ".env"


def get_stored_env_value(key: str) -> Optional[str]:
    """Reads a key from the local .env file if it exists."""
    if not ENV_PATH.exists():
        return None
    try:
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    if k.strip() == key:
                        return v.strip().strip("'\"")
    except Exception:
        pass
    return None


def save_env_value(key: str, value: str) -> None:
    """Appends or updates a key in .env safely."""
    lines = []
    found = False
    if ENV_PATH.exists():
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()

    new_lines = []
    for line in lines:
        if line.strip() and not line.strip().startswith("#") and "=" in line:
            k, _ = line.split("=", 1)
            if k.strip() == key:
                new_lines.append(f"{key}={value}\n")
                found = True
                continue
        new_lines.append(line)

    if not found:
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines.append("\n")
        new_lines.append(f"{key}={value}\n")

    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.writelines(new_lines)


def get_github_token() -> Tuple[Optional[str], Optional[str]]:
    """Resolves GitHub Token with priority:

    1. GITHUB_TOKEN environment variable or .env
    2. GitHub CLI (`gh auth token`)
    3. Interactive prompt / browser login assistance

    Returns:
        (token, username) or (None, None)
    """
    # 1. Check env or .env
    token = os.getenv("GITHUB_TOKEN") or get_stored_env_value("GITHUB_TOKEN")
    if token and token.strip() and not token.startswith("your_"):
        user = verify_github_token(token)
        if user:
            return token, user

    # 2. Check GitHub CLI (`gh`)
    if shutil.which("gh"):
        try:
            res = subprocess.run(
                ["gh", "auth", "token"],
                capture_output=True,
                text=True,
                check=False
            )
            gh_token = res.stdout.strip()
            if gh_token:
                user = verify_github_token(gh_token)
                if user:
                    return gh_token, user
        except Exception:
            pass

    return None, None


def interactive_github_login() -> Tuple[Optional[str], Optional[str]]:
    """Guides the user through logging into GitHub via gh CLI or browser."""
    print("\n" + "=" * 60)
    print("🔐 GITHUB LOGIN SETUP")
    print("=" * 60)

    # If gh is installed, offer 1-click gh auth login
    if shutil.which("gh"):
        print("💡 Found GitHub CLI ('gh') on your machine!")
        print("   You can log in directly using your browser via GitHub CLI.")
        choice = input("👉 Run 'gh auth login' now? [Y/n]: ").strip().lower()
        if choice in ("", "y", "yes"):
            try:
                subprocess.run(["gh", "auth", "login"], check=False)
                token, user = get_github_token()
                if token and user:
                    print(f"✅ Logged in to GitHub as @{user} via GitHub CLI!")
                    return token, user
            except Exception as e:
                print(f"⚠️  Could not run gh auth login: {e}")

    # Fallback: Browser Personal Access Token
    print("\nAlternative: Generate a free GitHub Token:")
    print("1. We will open GitHub Settings in your browser.")
    print("2. Click 'Generate token' (public_repo scope).")
    print("3. Paste the token below. It will be saved securely to your local .env.")

    open_browser = input("👉 Open GitHub token generation page in browser? [Y/n]: ").strip().lower()
    if open_browser in ("", "y", "yes"):
        webbrowser.open("https://github.com/settings/tokens/new?description=OSS-Project-Scout&scopes=public_repo")

    token = getpass.getpass("\n👉 Paste your GitHub Token (or press Enter to proceed unauthenticated): ").strip()
    if token:
        user = verify_github_token(token)
        if user:
            save_env_value("GITHUB_TOKEN", token)
            print(f"✅ Token verified! Connected as @{user}. Saved to local .env.")
            return token, user
        else:
            print("⚠️  Invalid GitHub token. Proceeding unauthenticated.")

    return None, None


def verify_github_token(token: str) -> Optional[str]:
    """Validates the token against GitHub API and returns the authenticated login username."""
    try:
        res = requests.get(
            "https://api.github.com/user",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "User-Agent": "OSS-Project-Scout/1.0"
            },
            timeout=5
        )
        if res.ok:
            return res.json().get("login")
    except Exception:
        pass
    return None


def get_gemini_api_key(prompt_if_missing: bool = True) -> Optional[str]:
    """Retrieves GEMINI_API_KEY from environment or .env, or prompts user once and saves it."""
    key = os.getenv("GEMINI_API_KEY") or get_stored_env_value("GEMINI_API_KEY")
    if key and key.strip() and not key.startswith("your_"):
        return key.strip()

    if not prompt_if_missing:
        return None

    print("\n" + "=" * 60)
    print("🤖 GEMINI API KEY SETUP")
    print("=" * 60)
    print("Get your free Gemini API key here: https://aistudio.google.com/apikey")
    try:
        entered_key = getpass.getpass("👉 Paste your Gemini API key (or press Enter to skip LLM features): ").strip()
        if entered_key:
            save_env_value("GEMINI_API_KEY", entered_key)
            print("✅ Gemini API key saved to local .env file! You will not be asked again.")
            return entered_key
    except EOFError:
        pass

    return None
