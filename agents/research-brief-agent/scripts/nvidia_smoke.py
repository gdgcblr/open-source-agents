#!/usr/bin/env python3
"""
Optional smoke check: GLM via NVIDIA integrate API + bundled fixture text.

This does NOT replace `agent-sdk eval` (which needs CURSOR_API_KEY). It verifies
that a OpenAI-compatible model can produce the structured report shape when given
the same fixture content the agent tools return.

Usage (from agents/research-brief-agent):
  pip install -r requirements-dev.txt
  set NVIDIA_API_KEY=...   # Windows
  npm run tool:read-fixture > .agent-serve/nvidia-fixture.json  # or pipe
  python scripts/nvidia_smoke.py --fixture-json .agent-serve/nvidia-fixture.json
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


def load_fixture_text(path: str) -> str:
    # utf-8-sig handles BOM written by PowerShell Out-File
    with open(path, encoding="utf-8-sig") as f:
        raw = f.read()
    # The SDK may prefix log lines (e.g. "[bdk] ...") before JSON.
    # Find the first line that starts with '{' and parse from there.
    json_start = raw.find('{')
    if json_start == -1:
        raise SystemExit(f"No JSON object found in fixture file: {path!r}")
    data = json.loads(raw[json_start:])
    if not data.get("ok"):
        raise SystemExit(f"fixture JSON not ok: {data!r}")
    return data["result"]["content"]


def main() -> int:
    parser = argparse.ArgumentParser(description="NVIDIA API structured-report smoke")
    parser.add_argument(
        "--fixture-json",
        required=True,
        help="Output from: npm run tool:read-fixture (agent-sdk tool JSON)",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("NVIDIA_MODEL", "z-ai/glm-5.3"),
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get(
            "NVIDIA_API_BASE_URL", "https://integrate.api.nvidia.com/v1"
        ),
    )
    args = parser.parse_args()

    api_key = os.environ.get("NVIDIA_API_KEY")
    if not api_key:
        print(
            "NVIDIA_API_KEY is not set. Add it to .env locally (never commit).",
            file=sys.stderr,
        )
        return 2

    try:
        from openai import OpenAI
    except ImportError:
        print("Install: pip install -r requirements-dev.txt", file=sys.stderr)
        return 2

    source_text = load_fixture_text(args.fixture_json)
    client = OpenAI(base_url=args.base_url, api_key=api_key)

    user_prompt = f"""You are simulating the Research Brief Agent.

Topic: edge computing in healthcare
Source file: healthcare-edge.md

Use ONLY the source text below. Write a structured research report with these
exact level-2 headings (in order):
{chr(10).join(REQUIRED_HEADINGS)}

Mention healthcare-edge.md in Sources.

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
    missing = [h for h in REQUIRED_HEADINGS if h not in reply]
    if missing:
        print("FAIL: missing headings:", missing, file=sys.stderr)
        print(reply[:2000], file=sys.stderr)
        return 1

    if not re.search(r"healthcare-edge\.md", reply, re.I):
        print("FAIL: Sources section should cite healthcare-edge.md", file=sys.stderr)
        return 1

    print("PASS: NVIDIA smoke — structured report shape OK")
    print(reply[:1500] + ("..." if len(reply) > 1500 else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
