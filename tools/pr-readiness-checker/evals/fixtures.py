"""Builds throwaway open-source-ai repositories for tests and evals.

Fixtures live in code, not as files on disk, for two reasons:
  * fake secrets are generated at runtime, so this repository never contains
    strings that GitHub push protection (or prcheck itself) would flag;
  * files such as .env or .venv/ would be ignored by git and never reach the PR.
"""

from __future__ import annotations

import random
import string
import subprocess
from importlib import resources
from pathlib import Path

GIT_IDENTITY = ["-c", "user.name=prcheck-fixture", "-c", "user.email=fixture@example.invalid",
                "-c", "commit.gpgsign=false", "-c", "core.autocrlf=false"]


# --- fake secrets (built by concatenation so no literal key exists in this file) ---

def _rand(rng: random.Random, alphabet: str, n: int) -> str:
    return "".join(rng.choice(alphabet) for _ in range(n))


ALNUM = string.ascii_letters + string.digits


def fake_google_key(rng: random.Random) -> str:
    return "AI" + "za" + _rand(rng, ALNUM + "_-", 35)


def fake_openai_key(rng: random.Random) -> str:
    return "sk-" + "proj-" + _rand(rng, ALNUM, 48)


def fake_anthropic_key(rng: random.Random) -> str:
    return "sk-" + "ant-" + "api03-" + _rand(rng, ALNUM + "_-", 90)


def fake_github_token(rng: random.Random) -> str:
    return "gh" + "p_" + _rand(rng, ALNUM, 36)


def fake_github_pat(rng: random.Random) -> str:
    return "github" + "_pat_" + _rand(rng, ALNUM + "_", 82)


def fake_aws_key(rng: random.Random) -> str:
    return "AK" + "IA" + _rand(rng, string.ascii_uppercase + string.digits, 16)


def fake_slack_token(rng: random.Random) -> str:
    return "xo" + "xb-" + _rand(rng, string.digits, 12) + "-" + _rand(rng, ALNUM, 24)


def fake_hf_token(rng: random.Random) -> str:
    return "h" + "f_" + _rand(rng, ALNUM, 34)


def fake_private_key(rng: random.Random) -> str:
    begin = "-----BEGIN " + "RSA PRIVATE" + " KEY-----"
    end = "-----END " + "RSA PRIVATE" + " KEY-----"
    return f"{begin}\n{_rand(rng, ALNUM + '+/', 64)}\n{end}"


def fake_generic_secret(rng: random.Random) -> str:
    # Mixed letters and digits with high entropy, assigned to a secret-looking name.
    return _rand(rng, string.ascii_letters, 12) + _rand(rng, string.digits, 6) + _rand(rng, ALNUM, 14)


# --- a project that passes every check ------------------------------------------

GOOD_README = """# Meeting Notes Summarizer

> Turns raw meeting transcripts into a short list of decisions and action items.

## Overview
Busy teams lose decisions in long transcripts. This tool reads a transcript file and prints the
decisions, owners and deadlines it finds. It is meant for developers who run meetings in English.

## Technical Stack
- Python 3.12, Gemini 3.6 Flash through the google-genai SDK.

## Architecture & Data Flow
The script reads the transcript, sends it to the model with a fixed prompt, and prints the result.

## Prerequisites
- Python 3.11 or newer and a Gemini API key from Google AI Studio.

## Installation & Setup
```bash
python -m venv .venv
pip install -r requirements.txt
```

## Configuration & Environment Variables
| Variable | Required | Description |
| :--- | :--- | :--- |
| `GEMINI_API_KEY` | Yes | Key used to call the model |

## How to Run
```bash
python main.py notes/standup.txt
```

## Example Input & Output
Input: a 40-line standup transcript. Output from a real run:
```
Decisions: ship v2 on Friday. Actions: Priya - update docs (Thu).
```

## How to Test
Run `pytest`; the tests use a recorded model response, so no key is needed.

## Known Limitations
Transcripts longer than about 50 pages are cut off. Only English was tested.

## Security & Privacy Considerations
The transcript is sent to the Gemini API. The key is read from the environment and never logged.

## Future Improvements
- Support speaker diarisation.

## License
Contributed under the repository's MIT license.
"""

GOOD_FILES: dict[str, str] = {
    "README.md": GOOD_README,
    "requirements.txt": "google-genai==2.33.0\n",
    ".gitignore": ".env\n.venv/\n__pycache__/\n",
    ".env.example": "GEMINI_API_KEY=your_gemini_api_key_here\nMODEL_NAME=gemini-3.6-flash\n",
    "main.py": "import os\nimport sys\n\nAPI_KEY = os.getenv('GEMINI_API_KEY')\n\n\ndef main():\n"
               "    print(open(sys.argv[1]).read()[:100])\n\n\nif __name__ == '__main__':\n    main()\n",
}

ROOT_FILES: dict[str, str] = {
    "README.md": "# open-source-ai\n",
    "CONTRIBUTING.md": "# Contributing\n",
    "agents/README.md": "# Agents\n\n| Agent Directory | Description |\n| :--- | :--- |\n",
    "tools/README.md": "# Tools\n\n| Tool Directory | Description |\n| :--- | :--- |\n",
    ".gitignore": ".env\n.env.*\n!.env.example\n.venv/\nvenv/\nnode_modules/\n__pycache__/\n",
}


def template_readme() -> str:
    return resources.files("prcheck").joinpath("data/template_readme.md").read_text(encoding="utf-8")


def write_files(root: Path, files: dict[str, str | None]) -> None:
    for rel, content in files.items():
        path = root / rel
        if content is None:
            if path.exists():
                path.unlink()
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", *GIT_IDENTITY, *args], cwd=root, check=True, capture_output=True)


def build_repo(
    root: Path,
    *,
    project: str = "tools/meeting-notes-summarizer",
    files: dict[str, str | None] | None = None,
    base_files: dict[str, str | None] | None = None,
    branch_files: dict[str, str | None] | None = None,
    use_git: bool = False,
) -> Path:
    """Create a fake repo under `root` and return the project folder.

    files        project files, merged over GOOD_FILES (None deletes a default file)
    base_files   extra repo files committed on the base branch `main` (git only)
    branch_files extra repo files changed on the feature branch (git only)
    """
    project_files = {**GOOD_FILES, **(files or {})}
    write_files(root, {**ROOT_FILES, "template/README.md": template_readme(), **(base_files or {})})
    if use_git:
        git(root, "init", "-q", "-b", "main")
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "base")
        git(root, "checkout", "-q", "-b", "feat/fixture")
    write_files(root / project, project_files)
    (root / project).mkdir(parents=True, exist_ok=True)
    write_files(root, branch_files or {})
    if use_git:
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "feature")
    return root / project
