#!/usr/bin/env python3
"""diff-risk-reviewer: summarise a git diff, flag risks, suggest tests.

Two layers:
  1. Static checks (offline, deterministic): secrets, risky files, missing
     tests, oversized changes, debug leftovers.
  2. LLM review (Gemini or Grok) for a plain-English summary and suggested tests.
     Use --mock to skip the LLM entirely (no API key needed).
"""
import argparse
import json
import os
import re
import sys

try:  # optional: load GEMINI_API_KEY from a local .env
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

DEFAULT_MODELS = {
    "gemini": "gemini-3.8-flash",  # override with --model or GEMINI_MODEL
    "grok": "grok-4.20-reasoning",  # override with --model or XAI_MODEL
}
MODEL_ENV = {"gemini": "GEMINI_MODEL", "grok": "XAI_MODEL"}
XAI_BASE_URL = "https://api.x.ai/v1"
MAX_DIFF_CHARS = 60_000
LARGE_CHANGE_LINES = 500
SEVERITY_ORDER = {"high": 3, "medium": 2, "low": 1}

SECRET_PATTERNS = [
    (r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", "Private key block"),
    (r"AKIA[0-9A-Z]{16}", "AWS access key ID"),
    (r"AIza[0-9A-Za-z_\-]{35}", "Google API key"),
    (
        r"(?i)(api[_-]?key|secret|token|passwd|password)\s*[=:]\s*[\"'][^\"']{8,}[\"']",
        "Hard-coded credential assignment",
    ),
]
RISKY_PATH_HINTS = [
    ("migration", "Database migration"),
    ("dockerfile", "Container build file"),
    (".github/workflows", "CI/CD workflow"),
    ("terraform", "Infrastructure as code"),
    (".env", "Environment/config file"),
    ("requirements", "Dependency manifest"),
    ("package.json", "Dependency manifest"),
    ("auth", "Authentication-related code"),
]
CODE_EXTENSIONS = (".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".kt")
DEBUG_PATTERN = re.compile(
    r"console\.log|breakpoint\(\)|pdb\.set_trace|\bdebugger\b|\bTODO\b|\bFIXME\b"
)


def parse_diff(text):
    """Return {path: {"added": [lines], "removed": int}} from a unified diff."""
    files, current = {}, None
    for line in text.splitlines():
        if line.startswith("diff --git"):
            m = re.match(r"diff --git a/(.+?) b/(.+)$", line)
            current = m.group(2) if m else line
            files[current] = {"added": [], "removed": 0}
        elif current and line.startswith("+") and not line.startswith("+++"):
            files[current]["added"].append(line[1:])
        elif current and line.startswith("-") and not line.startswith("---"):
            files[current]["removed"] += 1
    return files


def static_checks(files):
    """Deterministic risk checks. Returns a list of finding dicts."""
    findings = []

    def add(severity, title, detail):
        findings.append({"severity": severity, "title": title, "detail": detail})

    for path, info in files.items():
        for line in info["added"]:
            for pattern, label in SECRET_PATTERNS:
                if re.search(pattern, line):
                    add("high", f"Possible secret: {label}", f"{path} (value redacted)")
                    break

    for path in files:
        for hint, label in RISKY_PATH_HINTS:
            if hint in path.lower():
                add("medium", f"Sensitive file touched: {label}", path)
                break

    source = [p for p in files if p.endswith(CODE_EXTENSIONS) and "test" not in p.lower()]
    tests = [p for p in files if "test" in p.lower()]
    if source and not tests:
        add("medium", "Source changed without tests", ", ".join(source[:5]))

    total = sum(len(i["added"]) + i["removed"] for i in files.values())
    if total > LARGE_CHANGE_LINES:
        add("medium", "Large change", f"{total} changed lines; consider splitting the PR")

    for path, info in files.items():
        hits = [l.strip() for l in info["added"] if DEBUG_PATTERN.search(l)]
        if hits:
            add("low", "Debug/TODO leftovers", f"{path}: {len(hits)} line(s), e.g. `{hits[0][:60]}`")

    return findings


def stats(files):
    added = sum(len(i["added"]) for i in files.values())
    removed = sum(i["removed"] for i in files.values())
    return len(files), added, removed


def mock_review(files):
    n, a, r = stats(files)
    names = ", ".join(list(files)[:5]) + ("..." if n > 5 else "")
    return {
        "summary": f"[mock] {n} file(s) changed (+{a}/-{r}): {names}",
        "risks": [],
        "suggested_tests": ["[mock] Run with a real model (omit --mock) for test suggestions."],
    }


def build_prompt(diff_text, static):
    return (
        "You are a careful senior code reviewer. Review the git diff below.\n"
        "Return ONLY JSON with keys: summary (2-3 sentences), "
        'risks (list of {"severity": "high|medium|low", "title": str, "detail": str}), '
        "suggested_tests (list of short strings). Only report risks visible in the diff.\n"
        f"Already-detected static findings (do not repeat): {json.dumps(static)}\n\n"
        f"DIFF:\n{diff_text[:MAX_DIFF_CHARS]}"
    )


def parse_json_response(text):
    """Parse model JSON, tolerating ```json fences."""
    try:
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", (text or "").strip())
        return json.loads(cleaned)
    except (json.JSONDecodeError, TypeError):
        sys.exit("Model did not return valid JSON; try again or use --mock.")


def call_gemini(prompt, model):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        sys.exit("GEMINI_API_KEY is not set. Copy .env.example to .env or use --mock.")
    try:
        from google import genai
    except ImportError:
        sys.exit("Missing dependency: pip install -r requirements.txt")
    client = genai.Client(api_key=api_key)
    resp = client.models.generate_content(
        model=model, contents=prompt, config={"response_mime_type": "application/json"}
    )
    return resp.text


def call_grok(prompt, model):
    """xAI's API is OpenAI-compatible: same SDK, different base URL."""
    api_key = os.environ.get("XAI_API_KEY")
    if not api_key:
        sys.exit("XAI_API_KEY is not set. Copy .env.example to .env or use --mock.")
    try:
        from openai import OpenAI
    except ImportError:
        sys.exit("Missing dependency: pip install -r requirements.txt")
    client = OpenAI(api_key=api_key, base_url=XAI_BASE_URL)
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
    )
    return resp.choices[0].message.content


def llm_review(diff_text, static, provider, model):
    """Ask the chosen LLM for a summary, extra risks and suggested tests (JSON)."""
    prompt = build_prompt(diff_text, static)
    call = call_grok if provider == "grok" else call_gemini
    try:
        text = call(prompt, model)
    except SystemExit:
        raise
    except Exception as exc:  # API/network errors: show a short, actionable message
        hint = MODEL_ENV[provider]
        sys.exit(
            f"{provider} API call failed (model '{model}'): {str(exc)[:300]}\n"
            f"If the model is unavailable, set {hint} to a current model name."
        )
    return parse_json_response(text)


def render(files, findings, review):
    n, a, r = stats(files)
    lines = [f"# Diff Risk Report ({n} files, +{a}/-{r})", "", "## Summary", review["summary"], ""]
    ordered = sorted(findings, key=lambda f: -SEVERITY_ORDER.get(f["severity"], 0))
    lines.append("## Risks")
    if not ordered:
        lines.append("No risks detected.")
    for f in ordered:
        lines.append(f"- **[{f['severity'].upper()}]** {f['title']}: {f['detail']}")
    lines += ["", "## Suggested tests"]
    lines += [f"- {t}" for t in review.get("suggested_tests", [])] or ["- None"]
    return "\n".join(lines)


def main(argv=None):
    p = argparse.ArgumentParser(description="Review a git diff for risks.")
    p.add_argument("diff", help="Path to a diff file, or - for stdin")
    p.add_argument("--mock", action="store_true", help="Skip the LLM (no API key needed)")
    p.add_argument("--provider", choices=["gemini", "grok"],
                   default=os.environ.get("LLM_PROVIDER", "gemini").lower(),
                   help="LLM provider (default: $LLM_PROVIDER or gemini)")
    p.add_argument("--model", help="Model name (default depends on provider)")
    p.add_argument("--json", action="store_true", help="Output JSON instead of Markdown")
    p.add_argument("--fail-on", choices=["high", "medium"], help="Exit 1 at/above this severity")
    args = p.parse_args(argv)

    text = sys.stdin.read() if args.diff == "-" else open(args.diff, encoding="utf-8").read()
    files = parse_diff(text)
    if not files:
        sys.exit("No diff content found. Pipe in `git diff` output.")

    if args.provider not in DEFAULT_MODELS:
        sys.exit(f"Unknown provider '{args.provider}'. Use gemini or grok.")
    model = args.model or os.environ.get(MODEL_ENV[args.provider]) or DEFAULT_MODELS[args.provider]
    findings = static_checks(files)
    review = mock_review(files) if args.mock else llm_review(text, findings, args.provider, model)
    findings += [f for f in review.get("risks", []) if f.get("severity") in SEVERITY_ORDER]

    if args.json:
        print(json.dumps({"summary": review["summary"], "risks": findings,
                          "suggested_tests": review.get("suggested_tests", [])}, indent=2))
    else:
        print(render(files, findings, review))

    if args.fail_on:
        limit = SEVERITY_ORDER[args.fail_on]
        if any(SEVERITY_ORDER[f["severity"]] >= limit for f in findings):
            sys.exit(1)


if __name__ == "__main__":
    main()
