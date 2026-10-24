import os
import re
import json
from google import genai
from models import Finding, Severity

# Known malicious packages (subset of OpenSSF/PyPI Security WG confirmed cases)
_KNOWN_MALICIOUS = {
    "colourama", "requests-oauthlib2", "python-dateutil2", "urllib4",
    "python3-dateutil", "pythonkafka", "setup-tools", "setuptool",
    "install-requires", "requirements-parser2", "aiohttp-socks2",
    "pycrypto2", "crypto2", "cryptography2", "django-rest-framework2",
    "fastapi2", "uvicorn2", "starlette2", "httpx2", "pydantic2",
    "langchain-community2", "openai2", "anthropic2",
}

_DEP_FILE_PATTERNS = [
    r"requirements.*\.txt",
    r"pyproject\.toml",
    r"package\.json",
    r"package-lock\.json",
    r"Pipfile",
    r"setup\.py",
    r"setup\.cfg",
]
_DEP_COMPILED = [re.compile(p, re.IGNORECASE) for p in _DEP_FILE_PATTERNS]


def _extract_new_packages(diff: str) -> list[tuple[str, str]]:
    """Extract newly added package names from dependency file changes."""
    hits = []
    in_dep_file = False

    for i, line in enumerate(diff.splitlines(), 1):
        if line.startswith("+++"):
            filename = line[4:].strip()
            in_dep_file = any(p.search(filename) for p in _DEP_COMPILED)
            continue

        if not in_dep_file or not line.startswith("+"):
            continue

        content = line[1:].strip()
        if not content or content.startswith("#"):
            continue

        # Extract package name from common formats
        pkg = re.split(r"[>=<!~\[\s@]", content)[0].strip().lower()
        if pkg and len(pkg) > 1:
            hits.append((f"line {i}", pkg))

    return hits


def run(diff: str) -> list[Finding]:
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    packages = _extract_new_packages(diff)
    if not packages:
        return []

    findings = []

    # First pass: check known malicious list immediately
    for line_ref, pkg in packages:
        if pkg in _KNOWN_MALICIOUS:
            findings.append(Finding(
                agent="SupplyChainAgent",
                severity=Severity.CRITICAL,
                title=f"Known malicious package: {pkg}",
                description=f"'{pkg}' is a confirmed typosquat or malicious package in the OpenSSF malicious packages database.",
                line_ref=line_ref,
                confidence=0.99,
            ))

    # Second pass: ask Gemini to reason about suspicious naming patterns
    unknown = [(ref, pkg) for ref, pkg in packages if pkg not in _KNOWN_MALICIOUS]
    if not unknown:
        return findings

    pkg_list = "\n".join(f"[{ref}] {pkg}" for ref, pkg in unknown)

    prompt = f"""You are a software supply chain security expert.

Review these Python/Node.js package names newly added to a dependency file:

{pkg_list}

For each package, assess:
1. Is it a known typosquat of a popular package? (e.g. "colourama" vs "colorama", "reqests" vs "requests")
2. Does the name follow suspicious patterns used in supply chain attacks? (appending 2, adding hyphens, common-name variants)
3. Is it a legitimate well-known package?

Respond ONLY with a JSON array. Each element:
{{
  "line_ref": "<line reference>",
  "package": "<name>",
  "is_suspicious": true/false,
  "reason": "<brief explanation>",
  "severity": "CRITICAL|HIGH|MEDIUM|LOW",
  "confidence": 0.0-1.0
}}

Only flag packages that are genuinely suspicious. Return [] if all packages look legitimate.
"""

    response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
    raw = response.text.strip()

    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)

    try:
        results = json.loads(raw)
    except json.JSONDecodeError:
        return findings

    for r in results:
        if not r.get("is_suspicious"):
            continue
        findings.append(Finding(
            agent="SupplyChainAgent",
            severity=Severity(r.get("severity", "HIGH")),
            title=f"Suspicious package: {r.get('package', '')}",
            description=r.get("reason", ""),
            line_ref=r.get("line_ref"),
            confidence=float(r.get("confidence", 0.7)),
        ))

    return findings
