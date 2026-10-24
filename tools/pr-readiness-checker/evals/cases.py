"""Labelled cases for the rule-check eval.

Each case says which checks should flag it (and with what status). Every other
check that runs must pass or be skipped. Add a case whenever a check misfires on
a real contribution, so the miss can never come back.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Callable

from . import fixtures as fx

TEMPLATE_LEFTOVER = "- Feature 1: Brief description of the capability.\n"


@dataclass
class Case:
    name: str
    description: str
    expect: dict[str, str]  # check id -> expected status ("fail", "warn", "info")
    project: str = "tools/meeting-notes-summarizer"
    files: Callable[[random.Random], dict[str, str | None]] = lambda rng: {}
    base_files: dict[str, str | None] = field(default_factory=dict)
    branch_files: dict[str, str | None] = field(default_factory=dict)
    use_git: bool = False


def _readme_without(*headings: str) -> str:
    out, skipping = [], False
    for line in fx.GOOD_README.splitlines(keepends=True):
        if line.startswith("## "):
            skipping = line[3:].strip() in headings
        if not skipping:
            out.append(line)
    return "".join(out)


CASES: list[Case] = [
    # --- baseline --------------------------------------------------------------
    Case("good-project", "A complete, clean contribution.", {}),

    # --- structure ---------------------------------------------------------------
    Case("not-kebab-case", "Folder uses capitals and underscores.", {"S2": "fail"},
         project="tools/Meeting_Notes"),
    Case("generic-name", "Folder name says nothing about the project.", {"S3": "fail"}, project="tools/demo"),
    Case("wrong-location", "Project nested one level too deep.", {"S1": "fail"},
         project="tools/team-x/meeting-notes-summarizer"),
    Case("wrong-category", "Project in a folder that is not a category.", {"S1": "fail"},
         project="projects/meeting-notes-summarizer"),
    Case("no-gitignore", "Project has no .gitignore.", {"S4": "warn"}, files=lambda rng: {".gitignore": None}),

    # --- docs ----------------------------------------------------------------------
    Case("no-readme", "README.md missing.", {"D1": "fail"}, files=lambda rng: {"README.md": None}),
    Case("missing-required-sections", "README lacks testing and limitations sections.", {"D2": "fail"},
         files=lambda rng: {"README.md": _readme_without("How to Test", "Known Limitations")}),
    Case("missing-recommended-sections", "README lacks template-only sections.", {"D2": "warn"},
         files=lambda rng: {"README.md": _readme_without("Technical Stack", "Future Improvements")}),
    Case("template-leftovers", "README still has template filler.", {"D3": "warn"},
         files=lambda rng: {"README.md": fx.GOOD_README.replace("## Technical Stack\n",
                                                                "## Technical Stack\n" + TEMPLATE_LEFTOVER)}),
    Case("unfilled-template", "README is the untouched template.", {"D3": "warn"},
         files=lambda rng: {"README.md": fx.template_readme()}),
    Case("placeholder-quoted-in-code", "Quoting template text inside a code block (e.g. sample output) is fine.",
         {}, files=lambda rng: {"README.md": fx.GOOD_README.replace(
             "Decisions: ship v2 on Friday.", 'Decisions: ship v2. Linter said: "# [Project Name]" missing.')}),
    Case("slug-placeholder-in-code", "An install command still says <project-slug>.", {"D3": "warn"},
         files=lambda rng: {"README.md": fx.GOOD_README.replace(
             "python -m venv .venv\n", "cd tools/<project-slug>\npython -m venv .venv\n")}),
    Case("empty-section", "A section heading with nothing under it.", {"D4": "warn"},
         files=lambda rng: {"README.md": fx.GOOD_README.replace(
             "## Future Improvements\n- Support speaker diarisation.\n", "## Future Improvements\n\n")}),
    Case("bare-na", "A section that only says N/A.", {"D4": "warn"},
         files=lambda rng: {"README.md": fx.GOOD_README.replace(
             "## Future Improvements\n- Support speaker diarisation.\n", "## Future Improvements\nN/A\n")}),
    Case("na-with-reason", "N/A followed by a reason is fine.", {},
         files=lambda rng: {"README.md": fx.GOOD_README.replace(
             "## Future Improvements\n- Support speaker diarisation.\n",
             "## Future Improvements\nN/A - this is a one-off script for the event.\n")}),

    # --- dependencies ----------------------------------------------------------------
    Case("no-manifest", "No dependency manifest.", {"M1": "fail"}, files=lambda rng: {"requirements.txt": None}),
    Case("unpinned-deps", "Dependencies without versions.", {"M2": "info"},
         files=lambda rng: {"requirements.txt": "google-genai\nrich>=13\n"}),
    Case("package-json", "A Node project with a pinned package.json is fine.", {},
         files=lambda rng: {"requirements.txt": None,
                            "package.json": '{"dependencies": {"@google/genai": "1.30.0"}}\n'}),

    # --- secrets ---------------------------------------------------------------------
    Case("committed-dotenv", "A .env file with no keys in it is still forbidden.", {"X1": "fail"},
         files=lambda rng: {".env": "DEBUG=true\n"}),
    Case("committed-pem", "A private key file.", {"X1": "fail", "X2": "fail"},
         files=lambda rng: {"certs/server.pem": fx.fake_private_key(rng) + "\n"}),
    Case("service-account-json", "A cloud service-account file.", {"X1": "fail"},
         files=lambda rng: {"service-account-prod.json": '{"type": "service_account"}\n'}),
    Case("google-key-in-code", "Gemini key hard-coded in source.", {"X2": "fail"},
         files=lambda rng: {"config.py": f'GEMINI_API_KEY = "{fx.fake_google_key(rng)}"\n'}),
    Case("key-in-env-example", "Real-looking key in .env.example.", {"X2": "fail"},
         files=lambda rng: {".env.example": f"OPENAI_API_KEY={fx.fake_openai_key(rng)}\n"}),
    Case("github-token-in-readme", "Token pasted into the README example.", {"X2": "fail"},
         files=lambda rng: {"README.md": fx.GOOD_README.replace(
             "Run `pytest`", f"Set GH_TOKEN={fx.fake_github_token(rng)} then run `pytest`")}),
    Case("generic-secret", "A high-entropy value assigned to a secret-like name.", {"X2": "warn"},
         files=lambda rng: {"settings.py": f'db_password = "{fx.fake_generic_secret(rng)}"\n'}),
    Case("placeholders-are-fine", "Placeholder values must not be flagged.", {},
         files=lambda rng: {".env.example": "GEMINI_API_KEY=your_gemini_api_key_here\nAPI_TOKEN=<your-token>\n"
                                            "SECRET_KEY=changeme_changeme_123\n"}),
    Case("decoys-are-fine", "Hashes and IDs that are not secrets.", {},
         files=lambda rng: {"data.py": 'COMMIT = "4f9c2e1b7a3d5f6e8c0b1a2d3e4f5a6b7c8d9e0f"\n'
                                       'RUN_ID = "3f2b8c1e-9a4d-4e6f-b7c8-1d2e3f4a5b6c"\n'
                                       'token_count = 123456789012345678\n'
                                       'DISK_KEY_PATH = "/home/user/.config/app/settings.yaml"\n'}),
    Case("env-without-example", "Code reads env vars but has no .env.example.", {"X3": "warn"},
         files=lambda rng: {".env.example": None}),
    Case("committed-venv", "A virtual environment inside the project.", {"X4": "fail"},
         files=lambda rng: {".venv/pyvenv.cfg": "home = /usr/bin\n"}),
    Case("committed-node-modules", "node_modules inside the project.", {"X4": "fail"},
         files=lambda rng: {"web/node_modules/left-pad/index.js": "module.exports = 1\n"}),
    Case("committed-pycache", "Compiled Python caches.", {"X4": "fail"},
         files=lambda rng: {"__pycache__/main.cpython-312.pyc": "x"}),

    # --- git scope -------------------------------------------------------------------
    Case("git-clean", "Only the project folder changed.", {}, use_git=True),
    Case("git-index-row", "One row added to the category index is allowed.", {}, use_git=True,
         branch_files={"tools/README.md": fx.ROOT_FILES["tools/README.md"]
                       + "| meeting-notes-summarizer | Summarises meetings |\n"}),
    Case("git-index-rewrite", "Rewriting the index table is more than one row.", {"G1": "warn"}, use_git=True,
         branch_files={"tools/README.md": "# Tools\n\nRewritten.\n\nMore.\n\nEven more.\n"}),
    Case("git-out-of-scope", "Root README edited in the same PR.", {"G1": "fail"}, use_git=True,
         branch_files={"README.md": "# open-source-ai\n\nMy edit.\n"}),
    Case("git-other-category-index", "Editing the other category's index.", {"G1": "fail"}, use_git=True,
         branch_files={"agents/README.md": fx.ROOT_FILES["agents/README.md"] + "| x | y |\n"}),
    Case("git-root-manifest", "Dependencies added at the repo root.", {"G2": "fail"}, use_git=True,
         branch_files={"requirements.txt": "google-genai==2.33.0\n"}),
    Case("git-name-taken", "Folder already exists upstream.", {"G3": "warn"}, use_git=True,
         base_files={"tools/meeting-notes-summarizer/README.md": "# Someone else's project\n"}),
    Case("git-ignored-venv", "A local .venv that git ignores is fine.", {}, use_git=True,
         files=lambda rng: {".venv/pyvenv.cfg": "home = /usr/bin\n"}),
    Case("git-ignored-dotenv", "A local .env that git ignores is fine.", {}, use_git=True,
         files=lambda rng: {".env": "GEMINI_API_KEY=" + fx.fake_google_key(rng) + "\n"}),
]
