import re
import sys
from pathlib import Path

RULES = [
    (
        r"Could not resolve|Could not find .*artifact",
        "Gradle dependency failure",
        "Check dependency versions, repository URLs, and network access."
    ),
    (
        r"Compilation failed|cannot find symbol",
        "Compilation failure",
        "Review the compiler error and check your source code and dependencies."
    ),
    (
        r"401 Unauthorized|403 Forbidden|authentication failed",
        "Authentication or permission failure",
        "Check credentials, token expiry, and repository permissions."
    ),
    (
        r"Connection timed out|Connection refused",
        "Network connectivity failure",
        "Check network connectivity and whether the target service is running."
    ),
    (
        r"Quality Gate.*Failed|quality gate failed",
        "SonarQube quality gate failure",
        "Review the SonarQube report and investigate failed quality conditions."
    ),
    (
        r"OutOfMemoryError|Java heap space",
        "Possible memory exhaustion",
        "Review memory usage and JVM memory settings."
    ),
    (
        r"BUILD FAILED|script returned exit code [1-9]",
        "Build or pipeline step failed",
        "Inspect earlier log lines to identify the underlying error."
    ),
]


def analyze_log(log_text):
    findings = []

    for pattern, issue, suggestion in RULES:
        matching_lines = [
            line.strip()
            for line in log_text.splitlines()
            if re.search(pattern, line, re.IGNORECASE)
        ]

        if matching_lines:
            findings.append({
                "issue": issue,
                "suggestion": suggestion,
                "lines": matching_lines[:3],
            })

    return findings


def main():
    if len(sys.argv) != 2:
        print("Usage: python analyzer.py <log-file>")
        sys.exit(1)

    log_file = Path(sys.argv[1])

    if not log_file.is_file():
        print(f"Log file not found: {log_file}")
        sys.exit(1)

    log_text = log_file.read_text(
        encoding="utf-8",
        errors="replace"
    )

    findings = analyze_log(log_text)

    print("\n=== DevOps Pipeline Analyzer ===")

    if not findings:
        print("No recognized error patterns found.")
        print("Review the full log; this does not guarantee a successful build.")
        return

    for number, finding in enumerate(findings, start=1):
        print(f"\n{number}. Issue: {finding['issue']}")
        print(f"   Suggestion: {finding['suggestion']}")

        for line in finding["lines"]:
            print(f"   Log: {line}")

    print("\nAnalysis complete. Suggestions are not confirmed root causes.")


if __name__ == "__main__":
    main()