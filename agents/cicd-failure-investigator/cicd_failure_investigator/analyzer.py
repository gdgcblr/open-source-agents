"""Deterministic CI/CD log analysis."""

import re
from collections import Counter

PATTERNS = {
    "dependency_installation": [
        r"ModuleNotFoundError",
        r"ImportError",
        r"No matching distribution found",
        r"Could not find a version that satisfies the requirement",
        r"npm ERR!",
    ],
    "test_failure": [
        r"\bFAILED\b",
        r"AssertionError",
        r"\btests? failed\b",
        r"Test failed",
    ],
    "authentication": [
        r"\b401 Unauthorized\b",
        r"\b403 Forbidden\b",
        r"invalid_grant",
        r"invalid credentials",
        r"Permission denied",
    ],
    "configuration": [
        r"\bKeyError\b",
        r"ConfigurationError",
        r"missing environment variable",
        r"FileNotFoundError",
    ],
    "deployment": [
        r"Deployment failed",
        r"DEPLOYMENT_FAILED",
        r"DeploymentError",
        r"Error deploying",
    ],
}


def analyze_ci_log(log_text: str) -> dict:
    """Identify known CI/CD failure patterns in supplied log text."""
    if not isinstance(log_text, str) or not log_text.strip():
        return {
            "status": "error",
            "primary_category": "unknown",
            "category_counts": {},
            "evidence": [],
            "message": "Provide a non-empty CI/CD log as text.",
        }

    evidence = []
    category_counts = Counter()
    lines = log_text.splitlines()

    for category, patterns in PATTERNS.items():
        for pattern in patterns:
            for match in re.finditer(pattern, log_text, re.IGNORECASE):
                line_number = log_text.count("\n", 0, match.start()) + 1
                line = lines[line_number - 1].strip()

                evidence.append({
                    "category": category,
                    "pattern": pattern,
                    "line_number": line_number,
                    "line": line[:300],
                })
                category_counts[category] += 1

    if not evidence:
        return {
            "status": "no_known_failure_pattern",
            "primary_category": "unknown",
            "category_counts": {},
            "evidence": [],
            "message": (
                "No known failure pattern was detected. "
                "This does not prove that the pipeline succeeded."
            ),
        }

    primary_category = category_counts.most_common(1)[0][0]

    return {
        "status": "failure_detected",
        "primary_category": primary_category,
        "category_counts": dict(category_counts),
        "evidence": evidence[:50],
        "message": (
            "Patterns were detected in the log. "
            "Review the evidence before concluding the root cause."
        ),
    }