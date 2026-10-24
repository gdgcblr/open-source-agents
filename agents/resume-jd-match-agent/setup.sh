#!/usr/bin/env bash
# One-command setup for macOS / Linux. Run from agents/resume-jd-match-agent/:
#   ./setup.sh
# Creates .venv with Python 3.10+, installs dependencies, creates
# resume_jd_agent/.env from the template, and runs the offline tests.
set -euo pipefail
cd "$(dirname "$0")"

# 1. Find a Python 3.10+ interpreter (macOS often ships 3.9 as python3).
PYTHON=""
for candidate in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$candidate" >/dev/null 2>&1 &&
     "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
    PYTHON="$candidate"
    break
  fi
done
if [ -z "$PYTHON" ]; then
  echo "Error: Python 3.10 or newer is required. Install it (e.g. 'brew install python@3.11') and re-run." >&2
  exit 1
fi
echo "Using $("$PYTHON" --version) ($PYTHON)"

# 2. Virtual environment (recreated if it was built with an old Python).
if [ -x .venv/bin/python ] && ! .venv/bin/python -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
  echo "Existing .venv uses Python < 3.10; recreating it."
  rm -rf .venv
fi
[ -d .venv ] || "$PYTHON" -m venv .venv

# 3. Dependencies.
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install --quiet -r requirements.txt
echo "Installed: $(.venv/bin/pip show google-adk | grep Version | sed 's/Version: /google-adk /'), $(.venv/bin/pip show pypdf | grep Version | sed 's/Version: /pypdf /')"

# 4. API key file (never overwrite an existing one).
if [ ! -f resume_jd_agent/.env ]; then
  cp .env.example resume_jd_agent/.env
  echo "Created resume_jd_agent/.env: open it and replace 'your-key-here' with your Gemini API key."
elif grep -q "your-key-here" resume_jd_agent/.env; then
  echo "resume_jd_agent/.env still has the placeholder key: add your Gemini API key."
else
  echo "resume_jd_agent/.env already has a key."
fi

# 5. Offline tests (no API key or quota used).
.venv/bin/python -m unittest discover -s tests

echo
echo "Setup complete. Next:"
echo "  source .venv/bin/activate"
echo "  adk web            # browser UI at http://localhost:8000"
echo "  adk run resume_jd_agent   # terminal chat"
