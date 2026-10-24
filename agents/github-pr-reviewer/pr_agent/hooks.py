import os
import stat


HOOK_CONTENT = """#!/usr/bin/env bash
# Autonomous PR Reviewer & Triage Council Pre-Push Hook
# Automatically blocks pushes containing hardcoded credentials or critical flaws.

echo "🔍 Running Autonomous PR Reviewer Council pre-push security audit..."

DIFF_OUTPUT=$(git diff origin/main...HEAD 2>/dev/null || git diff HEAD~1 2>/dev/null)

if [ -z "$DIFF_OUTPUT" ]; then
    exit 0
fi

AGENT_DIR="{agent_dir}"
python3 "$AGENT_DIR/main.py" --stdin --offline --ci <<< "$DIFF_OUTPUT"
STATUS=$?

if [ $STATUS -ne 0 ]; then
    echo "🛑 Push rejected by Autonomous Security Council! Remediate critical issues before pushing."
    exit 1
fi

echo "✅ Pre-push audit passed. Proceeding with push."
exit 0
"""


def install_git_hook() -> bool:
    """Install pre-push hook into the parent git repository."""
    # Find .git directory
    current = os.path.dirname(os.path.abspath(__file__))
    git_dir = None
    walker = current
    while walker != "/":
        candidate = os.path.join(walker, ".git")
        if os.path.isdir(candidate):
            git_dir = candidate
            break
        walker = os.path.dirname(walker)

    if not git_dir:
        print("❌ Could not locate a .git directory to install hook.")
        return False

    hooks_dir = os.path.join(git_dir, "hooks")
    os.makedirs(hooks_dir, exist_ok=True)
    hook_path = os.path.join(hooks_dir, "pre-push")

    agent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    content = HOOK_CONTENT.replace("{agent_dir}", agent_dir)

    with open(hook_path, "w", encoding="utf-8") as f:
        f.write(content)

    # Make executable
    st = os.stat(hook_path)
    os.chmod(hook_path, st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    print(f"🎉 Pre-push Git hook successfully installed to: {hook_path}")
    print("Every `git push` will now automatically be audited by the Autonomous Council!")
    return True
