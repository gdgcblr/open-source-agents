#!/usr/bin/env python3
"""
smoke_test.py — Generic smoke check for the Research Brief Agent.

Verifies that any OpenAI-compatible model endpoint can produce the required
structured report shape when given the bundled fixture text. No provider is
hard-coded; all connection details come from environment variables.

Environment variables
---------------------
SMOKE_API_KEY      Required. API key for the model provider.
SMOKE_BASE_URL     Optional. Base URL of the OpenAI-compatible endpoint.
                   Default: https://api.openai.com/v1
SMOKE_MODEL        Optional. Model ID to use.
                   Default: gpt-4o-mini

Usage (from agents/research-brief-agent)
-----------------------------------------
  pip install -r requirements-dev.txt
  python scripts/save_fixture.py              # generates .agent-serve/fixture.json

  # Example — NVIDIA integrate endpoint
  set SMOKE_API_KEY=<your-key>
  set SMOKE_BASE_URL=https://integrate.api.nvidia.com/v1
  set SMOKE_MODEL=z-ai/glm-5.3

  # Example — OpenAI
  set SMOKE_API_KEY=<your-key>
  # (leave SMOKE_BASE_URL / SMOKE_MODEL at defaults or override)

  python scripts/smoke_test.py --fixture-json .agent-serve/fixture.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

REQUIRED_HEADINGS = (
    "## Executive Summary",
    "## Key Findings",
    "## Evidence Table",
    "## Risks & Uncertainties",
    "## Recommended Next Steps",
    "## Sources",
)

DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4o-mini"


def load_fixture_text(path: str) -> str:
    """Load the agent-sdk tool-call JSON fixture and return the source content."""
    # utf-8-sig handles BOM sometimes written by PowerShell Out-File
    with open(path, encoding="utf-8-sig") as f:
        raw = f.read()
    # SDK may prepend log lines before JSON; find first '{' to start parsing.
    json_start = raw.find("{")
    if json_start == -1:
        raise SystemExit(f"No JSON object found in fixture file: {path!r}")
    data = json.loads(raw[json_start:])
    if not data.get("ok"):
        raise SystemExit(f"Fixture JSON not ok: {data!r}")
    return data["result"]["content"]


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Generic smoke check: verifies structured report shape via any "
            "OpenAI-compatible endpoint. Configure via SMOKE_* env vars."
        )
    )
    parser.add_argument(
        "--fixture-json",
        required=True,
        help="Path to fixture JSON (output of: python scripts/save_fixture.py)",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("SMOKE_MODEL", DEFAULT_MODEL),
        help="Model ID to use (overrides SMOKE_MODEL env var)",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("SMOKE_BASE_URL", DEFAULT_BASE_URL),
        help="Base URL of the OpenAI-compatible API (overrides SMOKE_BASE_URL)",
    )
    args = parser.parse_args()

    api_key = os.environ.get("SMOKE_API_KEY")
    if not api_key:
        print(
            "ERROR: SMOKE_API_KEY is not set.\n"
            "  Export it in your shell before running (never commit the key):\n"
            "    Windows:  set SMOKE_API_KEY=<your-key>\n"
            "    Unix:     export SMOKE_API_KEY=<your-key>",
            file=sys.stderr,
        )
        return 2

    try:
        from openai import OpenAI
    except ImportError:
        print("Install deps first:  pip install -r requirements-dev.txt", file=sys.stderr)
        return 2

    source_text = load_fixture_text(args.fixture_json)
    client = OpenAI(base_url=args.base_url, api_key=api_key)

    print(f"[smoke] model={args.model}  base_url={args.base_url}")

    user_prompt = f"""You are simulating the Research Brief Agent.

Topic: edge computing in healthcare
Source file: healthcare-edge.md

Use ONLY the source text below. Write a structured research report with these
exact level-2 headings (in order):
{chr(10).join(REQUIRED_HEADINGS)}

Mention healthcare-edge.md in the Sources section.

--- SOURCE ---
{source_text}
--- END SOURCE ---"""

    completion = client.chat.completions.create(
        model=args.model,
        messages=[
            {
                "role": "system",
                "content": "You write concise, grounded research briefs. No invented URLs.",
            },
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,
        max_tokens=2048,
        stream=False,
    )

    reply = completion.choices[0].message.content or ""

    # --- assertions ---
    missing = [h for h in REQUIRED_HEADINGS if h not in reply]
    if missing:
        print("FAIL: missing headings:", missing, file=sys.stderr)
        print(reply[:2000], file=sys.stderr)
        return 1

    if not re.search(r"healthcare-edge\.md", reply, re.I):
        print("FAIL: Sources section should cite healthcare-edge.md", file=sys.stderr)
        return 1

    print("PASS: structured report shape OK")
    print(reply[:1500] + ("..." if len(reply) > 1500 else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
