#!/usr/bin/env python3
"""
git-commit-agent: Generates conventional commit messages from staged git diffs
using Google Agent Development Kit (ADK) and Gemini (with offline Ollama fallback).

Usage:
    python main.py                     # interactive: shows message, asks to commit
    python main.py --dry-run           # print generated message without committing
    python main.py -m "fix login bug"  # provide extra user context/hint
    python main.py --type feat         # enforce specific conventional commit type
    python main.py --scope auth        # enforce specific scope
    python main.py --amend             # generate message to amend the previous commit
    python main.py -a                  # stage modified/deleted files first (git add -u)
    python main.py -y                  # auto-commit without interactive prompt
    python main.py --provider ollama   # use local offline Ollama model
    python main.py --install-hook      # install prepare-commit-msg Git hook
    python main.py --uninstall-hook    # remove prepare-commit-msg Git hook
"""

import argparse
import asyncio
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from typing import Optional

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Environment & Configuration Setup
# ---------------------------------------------------------------------------

# Load .env from current working directory and from the script directory
load_dotenv()
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(SCRIPT_DIR, ".env"))

API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
if API_KEY:
    os.environ["GEMINI_API_KEY"] = API_KEY
    os.environ["GOOGLE_API_KEY"] = API_KEY

APP_NAME = "git-commit-agent"
USER_ID = "local-developer"

# ---------------------------------------------------------------------------
# Terminal Colors & Styling
# ---------------------------------------------------------------------------

class Colors:
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"

    @classmethod
    def disable(cls):
        cls.CYAN = ""
        cls.GREEN = ""
        cls.YELLOW = ""
        cls.RED = ""
        cls.BOLD = ""
        cls.DIM = ""
        cls.RESET = ""


def format_message_box(message: str) -> str:
    """Renders a clean divider box around the generated commit message."""
    border = "=" * 64
    return f"{Colors.CYAN}{border}\n{Colors.RESET}{message}\n{Colors.CYAN}{border}{Colors.RESET}"


# ---------------------------------------------------------------------------
# Security & Secret Scanning Guards
# ---------------------------------------------------------------------------

SECRET_PATTERNS = [
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "Private Cryptographic Key"),
    (r"AKIA[0-9A-Z]{16}", "AWS Access Key ID"),
    (r"gh[pousr]_[A-Za-z0-9_]{36,}", "GitHub Personal Access Token"),
    (r"AIza[0-9A-Za-z_-]{35}", "Google API Key"),
    (r"xox[baprs]-[A-Za-z0-9-]+", "Slack Token"),
    (r"sk-[A-Za-z0-9_-]{32,}", "OpenAI API Key"),
    (r"(?i)(?:api_key|apikey|secret|token|password)\s*[:=]\s*['\"][a-zA-Z0-9_\-\.]{10,}['\"]", "Hardcoded Secret / Password"),
]

SENSITIVE_FILENAMES = [
    r"^\.env(?:\..+)?$",
    r"^id_(?:rsa|ecdsa|ed25519)$",
    r".*\.(?:pem|p12|pfx|key|keystore)$",
    r".*credentials\.json$",
    r".*service_account.*\.json$",
]


def check_staged_for_secrets() -> list[str]:
    """
    Scans staged filenames and added diff lines for potential credentials or secrets.
    Returns a list of warning descriptions.
    """
    warnings = []

    # 1. Check staged filenames
    res = subprocess.run(
        ["git", "diff", "--staged", "--name-only"],
        capture_output=True,
        text=True,
    )
    staged_files = [f.strip() for f in res.stdout.splitlines() if f.strip()]
    for fname in staged_files:
        basename = os.path.basename(fname)
        if basename.endswith(".example") or basename.endswith(".template"):
            continue
        for pat in SENSITIVE_FILENAMES:
            if re.search(pat, basename, re.IGNORECASE):
                warnings.append(f"Potentially sensitive file staged: '{fname}'")
                break

    # 2. Check added lines in staged diff
    diff_res = subprocess.run(
        ["git", "diff", "--staged", "-U0"],
        capture_output=True,
        text=True,
    )
    for line in diff_res.stdout.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            added_text = line[1:].strip()
            lower = added_text.lower()
            if "example" in lower or "your_" in lower or "placeholder" in lower:
                continue
            for pat, desc in SECRET_PATTERNS:
                if re.search(pat, added_text):
                    snippet = added_text[:50] + "..." if len(added_text) > 50 else added_text
                    warnings.append(f"Possible {desc} detected: {snippet}")
                    break

    return warnings


# ---------------------------------------------------------------------------
# Branch Name Context & Issue Auto-Linking
# ---------------------------------------------------------------------------

def get_current_branch() -> str:
    """Retrieves current Git branch name."""
    res = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True)
    return res.stdout.strip() if res.returncode == 0 else ""


def extract_issue_from_branch(branch: str) -> Optional[str]:
    """
    Extracts issue or ticket ID from branch naming patterns.
    Examples:
      feat/issue-123-auth -> #123
      fix/GH-456          -> GH-456
      PROJ-789-desc       -> PROJ-789
      bugfix/42-fix-typo  -> #42
    """
    patterns = [
        r"(?:fix|feat|chore|bug|issue|refactor)[/-](?:issue-?|#)?([0-9]+)",
        r"([A-Z]{2,10}-[0-9]+)",
        r"(?:^|/)#?([0-9]{2,8})(?:-|$)",
    ]
    for p in patterns:
        m = re.search(p, branch, re.IGNORECASE)
        if m:
            val = m.group(1)
            return f"#{val}" if val.isdigit() else val.upper()
    return None


# ---------------------------------------------------------------------------
# ADK Tools — Plain Python functions inspected by Google ADK
# ---------------------------------------------------------------------------

def get_staged_file_summary() -> dict:
    """
    Returns a compact summary of files changed, their status (A/M/D/R),
    and line count statistics (--stat) to help understand scope and impact.
    """
    res_names = subprocess.run(
        ["git", "diff", "--staged", "--name-status"],
        capture_output=True,
        text=True,
    )
    res_stat = subprocess.run(
        ["git", "diff", "--staged", "--stat"],
        capture_output=True,
        text=True,
    )
    summary = (
        f"Files Changed:\n{res_names.stdout.strip()}\n\n"
        f"Stat Summary:\n{res_stat.stdout.strip()}"
    )
    return {"summary": summary}


def get_staged_diff(max_chars: int = 25000) -> dict:
    """
    Retrieves the code diff of all changes staged for commit.
    Filters out noise from generated lockfiles and limits total characters
    to prevent token overflows.
    """
    base_cmd = ["git", "diff", "--staged"]
    lockfile_excludes = [
        ":(exclude)*package-lock.json",
        ":(exclude)*yarn.lock",
        ":(exclude)*pnpm-lock.yaml",
        ":(exclude)*poetry.lock",
        ":(exclude)*Cargo.lock",
        ":(exclude)*Gemfile.lock",
        ":(exclude)*composer.lock",
        ":(exclude)*go.sum",
    ]

    result = subprocess.run(
        base_cmd + lockfile_excludes,
        capture_output=True,
        text=True,
    )
    diff = result.stdout.strip()

    # If diff was empty due to only lockfiles being changed, fall back to unfiltered diff
    if not diff:
        fallback = subprocess.run(base_cmd, capture_output=True, text=True)
        diff = fallback.stdout.strip()

    if not diff:
        return {"error": "no_staged_changes", "diff": ""}

    if len(diff) > max_chars:
        truncated = (
            diff[:max_chars]
            + f"\n\n[...diff truncated: showing first {max_chars} chars of {len(diff)}. "
            f"Refer to get_staged_file_summary for the complete list of touched files.]"
        )
        return {"error": "", "diff": truncated}

    return {"error": "", "diff": diff}


def get_last_commit_info() -> dict:
    """
    Retrieves the commit message and hash of the latest git commit (HEAD).
    Used when amending an existing commit.
    """
    result = subprocess.run(
        ["git", "log", "-1", "--pretty=format:Commit: %h%nSubject: %s%n%n%b"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return {"error": result.stderr.strip(), "last_commit": ""}
    return {"error": "", "last_commit": result.stdout.strip()}


def create_git_commit(message: str) -> dict:
    """
    Creates a git commit with the provided commit message.
    """
    result = subprocess.run(
        ["git", "commit", "-m", message],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return {"success": True, "output": result.stdout.strip()}
    return {"success": False, "output": result.stderr.strip()}


# ---------------------------------------------------------------------------
# Agent Definition & Instruction Prompt
# ---------------------------------------------------------------------------

INSTRUCTION = """
You are an expert software engineer specialising in clean git history.
Your job is to generate a single, precise commit message following the
Conventional Commits specification (https://www.conventionalcommits.org/).

## Workflow
1. Call get_staged_file_summary() to understand which files changed and change volume.
2. Call get_staged_diff() to inspect the code changes.
3. If amending, inspect get_last_commit_info() to review the existing commit message.
4. Analyse the changes and write ONE commit message.
5. Return ONLY the raw commit message text — do NOT wrap in markdown fences (no ```), do NOT include conversational prelude or explanations.

## Conventional Commit Format
<type>(<optional scope>): <short description>

[optional body — explain WHY and WHAT changed, not line-by-line how]

[optional footer(s) — BREAKING CHANGE: <explanation> or Closes #<issue>]

## Allowed Types
feat | fix | docs | style | refactor | test | chore | perf | ci | build | revert

## Strict Rules
- Subject line must be <= 72 characters.
- Use the imperative mood ("add feature", not "added feature" or "adds feature").
- Do not put a trailing period at the end of the subject line.
- Be specific: mention the relevant component, module, or function.
- If breaking changes exist, use `!` before the colon (e.g., `feat(api)!: break change`) or include `BREAKING CHANGE:` in the footer.
- Adhere strictly to any user hints, forced types, scope constraints, or ticket references provided.
"""


def clean_commit_message(msg: str) -> str:
    """Strips markdown code fences, backticks, or extra wrapping from the response."""
    msg = msg.strip()
    if msg.startswith("```"):
        lines = msg.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        msg = "\n".join(lines).strip()
    return msg


# ---------------------------------------------------------------------------
# Google ADK Runner Helpers
# ---------------------------------------------------------------------------

def run_with_adk(model_name: str, prompt: str, amend_mode: bool = False) -> tuple[object, str, str]:
    """Runs with Google ADK Agent and Runner."""
    from google.adk import Agent
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types

    tools = [get_staged_file_summary, get_staged_diff, create_git_commit]
    if amend_mode:
        tools.append(get_last_commit_info)

    agent = Agent(
        name="git_commit_agent",
        model=model_name,
        description="Generates conventional git commit messages from staged changes.",
        instruction=INSTRUCTION,
        tools=tools,
    )

    session_service = InMemorySessionService()
    session = asyncio.run(session_service.create_session(app_name=APP_NAME, user_id=USER_ID))

    runner = Runner(
        agent=agent,
        app_name=APP_NAME,
        session_service=session_service,
    )

    def send_message(p: str) -> str:
        message = types.Content(role="user", parts=[types.Part(text=p)])
        collected_text = []
        for event in runner.run(user_id=USER_ID, session_id=session.id, new_message=message):
            if event.is_final_response() and event.content and event.content.parts:
                for part in event.content.parts:
                    if getattr(part, "text", None):
                        collected_text.append(part.text)
        return clean_commit_message("".join(collected_text).strip())

    initial_message = send_message(prompt)
    return send_message, initial_message, "google-adk"


# ---------------------------------------------------------------------------
# Local Offline Ollama Fallback Provider
# ---------------------------------------------------------------------------

def run_with_ollama(model_name: str, prompt: str, amend_mode: bool = False) -> tuple[object, str, str]:
    """Queries a local Ollama instance (zero external cloud dependencies)."""
    ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")

    # Gather tool context manually
    summary = get_staged_file_summary()["summary"]
    diff = get_staged_diff()["diff"]
    last_commit = get_last_commit_info()["last_commit"] if amend_mode else ""

    history = [
        {"role": "system", "content": INSTRUCTION},
        {
            "role": "user",
            "content": f"{prompt}\n\nStaged Summary:\n{summary}\n\nStaged Diff:\n{diff}\n" + (f"\nLast Commit:\n{last_commit}" if last_commit else ""),
        },
    ]

    def call_ollama(msgs: list) -> str:
        url = f"{ollama_host}/api/chat"
        payload = json.dumps({"model": model_name, "messages": msgs, "stream": False}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return clean_commit_message(data.get("message", {}).get("content", "").strip())
        except Exception as e:
            raise RuntimeError(f"Ollama connection error at {ollama_host}: {e}")

    initial_response = call_ollama(history)
    history.append({"role": "assistant", "content": initial_response})

    def reply_ollama(follow_up: str) -> str:
        history.append({"role": "user", "content": follow_up})
        ans = call_ollama(history)
        history.append({"role": "assistant", "content": ans})
        return ans

    return reply_ollama, initial_response, "ollama"


# ---------------------------------------------------------------------------
# Git Hook Installation
# ---------------------------------------------------------------------------

def install_git_hook() -> bool:
    """Installs a prepare-commit-msg Git hook into .git/hooks/."""
    git_dir_res = subprocess.run(["git", "rev-parse", "--git-dir"], capture_output=True, text=True)
    if git_dir_res.returncode != 0:
        print(f"{Colors.RED}Error: Not inside a git repository.{Colors.RESET}", file=sys.stderr)
        return False

    git_dir = git_dir_res.stdout.strip()
    hooks_dir = os.path.join(git_dir, "hooks")
    os.makedirs(hooks_dir, exist_ok=True)
    hook_path = os.path.join(hooks_dir, "prepare-commit-msg")

    py_exec = sys.executable
    script_abs = os.path.abspath(__file__)

    hook_content = f"""#!/usr/bin/env bash
# Installed by git-commit-agent
COMMIT_MSG_FILE=$1
COMMIT_SOURCE=$2
SHA=$3

if [ -z "$COMMIT_SOURCE" ]; then
    SUGGESTED=$("{py_exec}" "{script_abs}" --dry-run --no-color 2>/dev/null)
    if [ -n "$SUGGESTED" ]; then
        echo "$SUGGESTED" > "$COMMIT_MSG_FILE.tmp"
        cat "$COMMIT_MSG_FILE" >> "$COMMIT_MSG_FILE.tmp"
        mv "$COMMIT_MSG_FILE.tmp" "$COMMIT_MSG_FILE"
    fi
fi
"""
    with open(hook_path, "w", encoding="utf-8") as f:
        f.write(hook_content)

    st = os.stat(hook_path)
    os.chmod(hook_path, st.st_mode | stat.S_IEXEC)

    print(f"{Colors.GREEN}✓ Successfully installed 'prepare-commit-msg' hook at:{Colors.RESET} {hook_path}")
    print("Now whenever you run 'git commit', git-commit-agent will automatically prefill your commit message buffer!")
    return True


def uninstall_git_hook() -> bool:
    """Removes the prepare-commit-msg Git hook."""
    git_dir_res = subprocess.run(["git", "rev-parse", "--git-dir"], capture_output=True, text=True)
    if git_dir_res.returncode != 0:
        print(f"{Colors.RED}Error: Not inside a git repository.{Colors.RESET}", file=sys.stderr)
        return False

    hook_path = os.path.join(git_dir_res.stdout.strip(), "hooks", "prepare-commit-msg")
    if os.path.exists(hook_path):
        os.remove(hook_path)
        print(f"{Colors.GREEN}✓ Successfully removed Git hook at:{Colors.RESET} {hook_path}")
    else:
        print(f"{Colors.YELLOW}No prepare-commit-msg hook found at {hook_path}.{Colors.RESET}")
    return True


# ---------------------------------------------------------------------------
# Git Execution Helpers
# ---------------------------------------------------------------------------

def is_git_repository() -> bool:
    """Checks whether the current working directory is inside a git working tree."""
    res = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], capture_output=True, text=True)
    return res.returncode == 0 and res.stdout.strip() == "true"


def execute_git_commit(message: str, amend: bool = False) -> tuple[bool, str]:
    """Executes git commit directly."""
    cmd = ["git", "commit"]
    if amend:
        cmd.append("--amend")
    cmd.extend(["-m", message])

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        return True, result.stdout.strip()
    return False, result.stderr.strip()


def edit_message_in_editor(message: str) -> str:
    """Opens the user's preferred editor to modify the generated commit message."""
    editor = os.getenv("EDITOR") or os.getenv("VISUAL") or "vi"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as tmp:
        tmp.write(message)
        tmp_path = tmp.name

    try:
        subprocess.run([editor, tmp_path], check=True)
        with open(tmp_path, "r", encoding="utf-8") as f:
            edited = f.read().strip()
        return edited
    except Exception as e:
        print(f"{Colors.RED}Error launching editor '{editor}': {e}{Colors.RESET}", file=sys.stderr)
        return message
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Generate conventional git commit messages from staged changes using Google ADK and Gemini."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the generated message without committing.",
    )
    parser.add_argument(
        "-m", "--hint",
        type=str,
        default="",
        help="Provide optional user context or intent to guide the commit message (e.g. 'closes #42').",
    )
    parser.add_argument(
        "-t", "--type",
        type=str,
        default="",
        choices=["feat", "fix", "docs", "style", "refactor", "perf", "test", "build", "ci", "chore", "revert"],
        help="Enforce a specific Conventional Commit type.",
    )
    parser.add_argument(
        "-s", "--scope",
        type=str,
        default="",
        help="Enforce a specific Conventional Commit scope (e.g. 'auth', 'parser').",
    )
    parser.add_argument(
        "-a", "--all",
        action="store_true",
        help="Stage all modified and deleted tracked files before running (like 'git commit -a').",
    )
    parser.add_argument(
        "--amend",
        action="store_true",
        help="Analyze changes and generate a message to amend the previous commit.",
    )
    parser.add_argument(
        "-y", "--yes",
        action="store_true",
        help="Automatically commit using the generated message without prompting for confirmation.",
    )
    parser.add_argument(
        "--provider",
        type=str,
        default="auto",
        choices=["auto", "adk", "ollama"],
        help="Provider to use: 'adk' (Google Gemini), 'ollama' (offline local model), or 'auto'.",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="",
        help="Model override (Gemini model or Ollama model name).",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable ANSI color output.",
    )
    parser.add_argument(
        "--install-hook",
        action="store_true",
        help="Install git-commit-agent as a 'prepare-commit-msg' hook into the local repository.",
    )
    parser.add_argument(
        "--uninstall-hook",
        action="store_true",
        help="Remove git-commit-agent 'prepare-commit-msg' hook from the local repository.",
    )

    args = parser.parse_args()

    if args.no_color or not sys.stdout.isatty():
        Colors.disable()

    # Hook management operations
    if args.install_hook:
        sys.exit(0 if install_git_hook() else 1)
    if args.uninstall_hook:
        sys.exit(0 if uninstall_git_hook() else 1)

    # 1. Verify Git working tree
    if not is_git_repository():
        print(f"{Colors.RED}Error: Not a git repository (or any of the parent directories).{Colors.RESET}", file=sys.stderr)
        sys.exit(1)

    # 2. Automatically stage tracked changes if -a / --all is supplied
    if args.all:
        add_result = subprocess.run(["git", "add", "-u"], capture_output=True, text=True)
        if add_result.returncode != 0:
            print(f"{Colors.RED}Error staging changes: {add_result.stderr.strip()}{Colors.RESET}", file=sys.stderr)
            sys.exit(1)

    # 3. Check for staged changes or amend target
    if args.amend:
        head_check = subprocess.run(["git", "rev-parse", "--verify", "HEAD"], capture_output=True, text=True)
        if head_check.returncode != 0:
            print(f"{Colors.RED}Error: Cannot amend — repository has no commits yet.{Colors.RESET}", file=sys.stderr)
            sys.exit(1)
    else:
        staged_check = subprocess.run(["git", "diff", "--staged", "--name-only"], capture_output=True, text=True)
        if not staged_check.stdout.strip():
            print(f"{Colors.YELLOW}No staged changes found. Stage changes with `git add` or pass `-a` to stage all modified files.{Colors.RESET}")
            sys.exit(0)

    # 4. Security & Secret Check
    secret_warnings = check_staged_for_secrets()
    if secret_warnings:
        print(f"\n{Colors.RED}{Colors.BOLD}⚠️  SECURITY WARNING: Potential secrets or credentials detected in staged changes!{Colors.RESET}")
        for w in secret_warnings:
            print(f"  {Colors.YELLOW}• {w}{Colors.RESET}")
        print(f"\n{Colors.RED}Sending credentials to external LLM APIs can compromise security.{Colors.RESET}")
        if args.yes:
            print(f"{Colors.RED}Aborting auto-commit due to detected secrets.{Colors.RESET}", file=sys.stderr)
            sys.exit(1)
        try:
            proceed = input("Do you really want to proceed? [y/N]: ").strip().lower()
            if proceed not in ("y", "yes"):
                print(f"{Colors.YELLOW}Aborted by user.{Colors.RESET}")
                sys.exit(1)
        except (KeyboardInterrupt, EOFError):
            print(f"\n{Colors.YELLOW}Aborted by user.{Colors.RESET}")
            sys.exit(1)

    # 5. Determine Provider & Model
    has_api_key = bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))
    provider = args.provider

    if provider == "auto":
        if has_api_key:
            provider = "adk"
        else:
            provider = "ollama"

    if provider == "adk" and not has_api_key:
        print(f"{Colors.RED}Error: GEMINI_API_KEY or GOOGLE_API_KEY is not set.{Colors.RESET}", file=sys.stderr)
        print("To use Google ADK with Gemini, set GEMINI_API_KEY or pass --provider ollama for offline use:")
        print(f"  cp {os.path.join(SCRIPT_DIR, '.env.example')} {os.path.join(SCRIPT_DIR, '.env')}")
        print("Get an API key free at: https://aistudio.google.com/app/apikey")
        sys.exit(1)

    # 6. Construct prompt with branch context & constraints
    prompt_lines = ["Analyse the staged git changes and generate a conventional commit message."]
    current_branch = get_current_branch()
    branch_issue = extract_issue_from_branch(current_branch)

    if branch_issue:
        prompt_lines.append(f"Current branch '{current_branch}' references issue/ticket {branch_issue}. Consider referencing it in the commit footer if appropriate.")
    if args.hint:
        prompt_lines.append(f"User context/intent: {args.hint}")
    if args.type:
        prompt_lines.append(f"Enforce commit type: '{args.type}'")
    if args.scope:
        prompt_lines.append(f"Enforce commit scope: '{args.scope}'")
    if args.amend:
        prompt_lines.append("Note: This is an --amend commit. Call get_last_commit_info() to inspect the previous commit.")

    initial_prompt = "\n".join(prompt_lines)

    # 7. Execute Agent
    model_name = args.model
    if provider == "adk":
        model_name = model_name or os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
        print(f"\n{Colors.CYAN}Analysing staged changes with Google ADK ({model_name})...{Colors.RESET}\n")
        reply_fn, commit_message, _ = run_with_adk(model_name, initial_prompt, amend_mode=args.amend)
    else:
        model_name = model_name or os.getenv("OLLAMA_MODEL", "qwen2.5-coder:latest")
        print(f"\n{Colors.CYAN}Analysing staged changes with local Ollama ({model_name})...{Colors.RESET}\n")
        try:
            reply_fn, commit_message, _ = run_with_ollama(model_name, initial_prompt, amend_mode=args.amend)
        except Exception as err:
            print(f"{Colors.RED}Error connecting to Ollama: {err}{Colors.RESET}", file=sys.stderr)
            print("Ensure Ollama is running (`ollama serve`) or provide a GEMINI_API_KEY.")
            sys.exit(1)

    if not commit_message:
        print(f"{Colors.RED}Agent did not return a commit message. Please try again.{Colors.RESET}", file=sys.stderr)
        sys.exit(1)

    print(format_message_box(commit_message))

    # 8. Interactive loop
    while True:
        if args.dry_run:
            print(f"\n{Colors.YELLOW}[dry-run] No commit was made.{Colors.RESET}")
            return

        if args.yes:
            print("\nAuto-committing (--yes specified)...")
            answer = "y"
        else:
            try:
                answer = input(
                    f"\nUse this commit message? ["
                    f"{Colors.GREEN}y{Colors.RESET}es / "
                    f"{Colors.RED}n{Colors.RESET}o / "
                    f"{Colors.CYAN}e{Colors.RESET}dit / "
                    f"{Colors.YELLOW}r{Colors.RESET}egenerate]: "
                ).strip().lower()
            except (KeyboardInterrupt, EOFError):
                print(f"\n{Colors.RED}Aborted by user.{Colors.RESET}")
                sys.exit(0)

        if answer in ("y", "yes"):
            success, output = execute_git_commit(commit_message, amend=args.amend)
            if success:
                print(f"\n{Colors.GREEN}✓ Commit created successfully!{Colors.RESET}")
                if output:
                    print(f"{Colors.DIM}{output}{Colors.RESET}")
            else:
                print(f"\n{Colors.RED}Commit failed:{Colors.RESET}\n{output}", file=sys.stderr)
                sys.exit(1)
            break

        elif answer in ("e", "edit"):
            edited = edit_message_in_editor(commit_message)
            if not edited:
                print(f"{Colors.YELLOW}Empty commit message. Commit cancelled.{Colors.RESET}")
                sys.exit(0)
            commit_message = edited
            print(f"\n{Colors.CYAN}Updated commit message:{Colors.RESET}")
            print(format_message_box(commit_message))
            continue

        elif answer in ("r", "regenerate"):
            try:
                feedback = input(
                    f"{Colors.CYAN}Enter instructions for regeneration (or press Enter for default): {Colors.RESET}"
                ).strip()
            except (KeyboardInterrupt, EOFError):
                print(f"\n{Colors.YELLOW}Cancelled.{Colors.RESET}")
                sys.exit(0)

            regen_prompt = "Please regenerate the conventional commit message."
            if feedback:
                regen_prompt += f" Incorporate the following user feedback: {feedback}"

            print(f"\n{Colors.CYAN}Regenerating commit message ({model_name})...{Colors.RESET}\n")
            try:
                new_msg = reply_fn(regen_prompt)
                if new_msg:
                    commit_message = new_msg
                    print(format_message_box(commit_message))
                else:
                    print(f"{Colors.RED}Regeneration did not produce a message. Retaining current message.{Colors.RESET}")
            except Exception as e:
                print(f"{Colors.RED}Error during regeneration: {e}{Colors.RESET}")
            continue

        else:
            print(f"\n{Colors.YELLOW}Commit cancelled.{Colors.RESET}")
            break


if __name__ == "__main__":
    main()
