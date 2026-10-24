#!/usr/bin/env python3
"""
generate_report.py — Generate a full structured research brief via any
OpenAI-compatible model endpoint (NVIDIA, OpenAI, Anthropic, etc.).

This script is a standalone demo that does NOT require the BDK agent-sdk or
a CURSOR_API_KEY. It talks directly to the model API you configure.

Environment variables
---------------------
SMOKE_API_KEY      Required. API key for the model provider.
SMOKE_BASE_URL     Optional. Default: https://integrate.api.nvidia.com/v1
SMOKE_MODEL        Optional. Default: z-ai/glm-5.3

Usage
-----
  # Offline demo using bundled healthcare-edge.md fixture:
  python scripts/generate_report.py --topic "Edge Computing in Healthcare"

  # With your own URL as the source:
  python scripts/generate_report.py \\
      --topic "AI Agents in Drug Discovery" \\
      --url   "https://en.wikipedia.org/wiki/Drug_discovery"

  # Override model on the fly:
  python scripts/generate_report.py \\
      --topic "Quantum Computing Threats to Cryptography" \\
      --url   "https://en.wikipedia.org/wiki/Post-quantum_cryptography" \\
      --model "meta/llama-3.3-70b-instruct"
"""

from __future__ import annotations

import argparse
import json
import os
import re
import ssl
import sys
import textwrap
import urllib.request
from pathlib import Path

# Some Windows installs have outdated CA bundles; create a permissive context
# only for this demo fetcher (never for auth-sensitive calls).
_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE

# ── defaults ──────────────────────────────────────────────────────────────────
DEFAULT_BASE_URL = "https://integrate.api.nvidia.com/v1"
DEFAULT_MODEL    = "z-ai/glm-5.3"
MAX_BYTES        = 80_000    # cap raw HTTP response (bytes)
MODEL_INPUT_CHARS = 6_000   # max source chars sent to model (keeps prompt < ~3K tokens)
FIXTURE_PATH     = (
    Path(__file__).parent.parent
    / "bot/sandbox/workspace/sources/healthcare-edge.md"
)

REPORT_SCHEMA = (
    "## Executive Summary",
    "## Key Findings",
    "## Evidence Table",
    "## Risks & Uncertainties",
    "## Recommended Next Steps",
    "## Sources",
)

SYSTEM_PROMPT = textwrap.dedent("""\
    You are a senior research analyst. Write a grounded, structured research brief.
    Rules:
    - Use ONLY information from the provided source text. Do NOT invent facts, URLs, or statistics.
    - Include an Evidence Table formatted as a Markdown table with columns:
      Finding | Supporting Quote | Source
    - Every claim in Key Findings must appear in the Evidence Table.
    - Cite the source by name in the ## Sources section.
    - Be concise but thorough. Avoid filler phrases.
""")


# ── helpers ───────────────────────────────────────────────────────────────────

def fetch_url(url: str) -> str:
    """Fetch plain text from a public URL (strips HTML tags)."""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "research-brief-agent/1.0 (demo)"},
    )
    with urllib.request.urlopen(req, timeout=15, context=_SSL_CTX) as resp:
        raw = resp.read(MAX_BYTES).decode("utf-8", errors="replace")
    content_type = resp.headers.get("Content-Type", "")
    if "html" in content_type:
        raw = re.sub(r"<script[\s\S]*?</script>", " ", raw, flags=re.I)
        raw = re.sub(r"<style[\s\S]*?</style>",  " ", raw, flags=re.I)
        raw = re.sub(r"<[^>]+>", " ", raw)
        raw = re.sub(r"\s+", " ", raw).strip()
    return raw


def load_fixture() -> tuple[str, str]:
    """Return (source_name, source_text) for the bundled fixture."""
    if not FIXTURE_PATH.exists():
        raise SystemExit(
            f"Bundled fixture not found at {FIXTURE_PATH}.\n"
            "Run from agents/research-brief-agent or pass --url."
        )
    return "healthcare-edge.md (bundled fixture)", FIXTURE_PATH.read_text(encoding="utf-8")


def build_prompt(topic: str, source_name: str, source_text: str) -> str:
    heading_list = "\n".join(REPORT_SCHEMA)
    # Hard-cap source to keep prompt within model context limits
    trimmed = source_text[:MODEL_INPUT_CHARS]
    if len(source_text) > MODEL_INPUT_CHARS:
        trimmed += "\n[...source truncated for brevity...]\n"
    return textwrap.dedent(f"""\
        Topic: {topic}
        Source: {source_name}

        Write a structured research brief using ONLY the source text below.
        Use these exact level-2 headings in order:
        {heading_list}

        Cite "{source_name}" in the ## Sources section.

        --- SOURCE TEXT ---
        {trimmed}
        --- END SOURCE TEXT ---
    """)


def validate(report: str, source_name: str) -> list[str]:
    issues = []
    for heading in REPORT_SCHEMA:
        if heading not in report:
            issues.append(f"Missing heading: {heading}")
    # Check source is cited (flexible match on filename stem)
    stem = Path(source_name).stem if "." in source_name else source_name[:30]
    if not re.search(re.escape(stem), report, re.I):
        issues.append(f"Sources section does not mention: {source_name!r}")
    return issues


def force_utf8_stdout() -> None:
    """Re-open stdout/stderr as UTF-8 on Windows (avoids cp1252 errors)."""
    import io
    if hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass
    else:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    force_utf8_stdout()
    parser = argparse.ArgumentParser(
        description="Generate a structured research brief via any OpenAI-compatible API."
    )
    parser.add_argument("--topic", required=True, help="Research topic / question")
    parser.add_argument(
        "--url", default=None,
        help="Public URL to use as source. Omit to use the bundled healthcare-edge.md demo.",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("SMOKE_MODEL", DEFAULT_MODEL),
        help="Model ID (overrides SMOKE_MODEL env var)",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("SMOKE_BASE_URL", DEFAULT_BASE_URL),
        help="API base URL (overrides SMOKE_BASE_URL env var)",
    )
    parser.add_argument(
        "--out", default=None,
        help="Optional path to write the report Markdown file",
    )
    args = parser.parse_args()

    api_key = os.environ.get("SMOKE_API_KEY")
    if not api_key:
        print(
            "ERROR: SMOKE_API_KEY is not set.\n"
            "  Windows:  set SMOKE_API_KEY=<your-key>\n"
            "  Unix:     export SMOKE_API_KEY=<your-key>",
            file=sys.stderr,
        )
        return 2

    try:
        from openai import OpenAI
    except ImportError:
        print("Run:  pip install -r requirements-dev.txt", file=sys.stderr)
        return 2

    # ── load source ──────────────────────────────────────────────────────────
    if args.url:
        print(f"[generate_report] Fetching: {args.url}")
        try:
            source_text = fetch_url(args.url)
            source_name = args.url
        except Exception as exc:
            print(f"ERROR fetching URL: {exc}", file=sys.stderr)
            return 1
        print(f"[generate_report] Fetched {len(source_text):,} chars")
    else:
        source_name, source_text = load_fixture()
        print(f"[generate_report] Using bundled fixture: {source_name}")

    print(f"[generate_report] model={args.model}  base_url={args.base_url}")
    print(f"[generate_report] topic={args.topic!r}\n")

    # ── call model ───────────────────────────────────────────────────────────
    client   = OpenAI(base_url=args.base_url, api_key=api_key)
    prompt   = build_prompt(args.topic, source_name, source_text)
    response = client.chat.completions.create(
        model=args.model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
        ],
        temperature=0.3,
        max_tokens=3000,
        stream=False,
    )
    report = response.choices[0].message.content or ""

    if not report.strip():
        print("ERROR: Model returned an empty response.", file=sys.stderr)
        print(f"  finish_reason : {response.choices[0].finish_reason}", file=sys.stderr)
        print(f"  usage         : {response.usage}", file=sys.stderr)
        return 1

    # ── validate ─────────────────────────────────────────────────────────────
    issues = validate(report, source_name)
    status = "PASS" if not issues else f"WARN - {issues}"
    print(f"Validation: {status}\n")
    print("=" * 72)
    print(report)
    print("=" * 72)

    if args.out:
        out_path = Path(args.out)
        out_path.write_text(report, encoding="utf-8")
        print(f"\nReport saved to: {out_path}")

    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
