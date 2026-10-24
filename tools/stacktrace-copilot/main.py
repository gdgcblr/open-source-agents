"""StackTrace Copilot: deterministic error-log analysis."""

import argparse
import json
import re
from pathlib import Path


PYTHON_FRAME = re.compile(
    r'^\s*File "([^"]+)", line (\d+), in (.+)$'
)

JS_FRAME = re.compile(
    r'^\s*at\s+(?:(.*?)\s+\()?(.+?):(\d+):(\d+)\)?$'
)

ERROR_TYPES = (
    "ModuleNotFoundError",
    "ImportError",
    "AttributeError",
    "TypeError",
    "ValueError",
    "KeyError",
    "IndexError",
    "NameError",
    "AssertionError",
    "PermissionError",
    "FileNotFoundError",
    "ConnectionError",
    "TimeoutError",
    "SyntaxError",
    "RuntimeError",
)


def extract_error(lines):
    """Find the most likely exception or error message."""
    for line in reversed(lines):
        text = line.strip()
        if not text:
            continue

        for error_type in ERROR_TYPES:
            if text.startswith(error_type + ":") or text == error_type:
                return {
                    "type": error_type,
                    "message": text,
                }

        if re.match(r"^(Error|Exception):", text):
            return {
                "type": text.split(":", 1)[0],
                "message": text,
            }

    return {
        "type": "UnknownError",
        "message": "No recognized exception message was found.",
    }


def extract_frames(lines):
    """Extract source locations from Python and JavaScript stack traces."""
    frames = []

    for line in lines:
        match = PYTHON_FRAME.match(line)
        if match:
            frames.append({
                "file": match.group(1),
                "line": int(match.group(2)),
                "function": match.group(3),
            })
            continue

        match = JS_FRAME.match(line)
        if match:
            frames.append({
                "file": match.group(2),
                "line": int(match.group(3)),
                "column": int(match.group(4)),
                "function": match.group(1) or "<anonymous>",
            })

    return frames


def diagnose(error):
    """Return conservative, rule-based suggestions."""
    error_type = error["type"]
    message = error["message"]

    rules = {
        "ModuleNotFoundError": (
            "A Python module could not be imported.",
            [
                "Check the module name and spelling.",
                "Verify that the dependency is installed in the active environment.",
                "Confirm that the correct virtual environment is activated.",
            ],
        ),
        "ImportError": (
            "A requested import could not be resolved.",
            [
                "Check the imported symbol and package version.",
                "Inspect circular imports and package initialization.",
            ],
        ),
        "AttributeError": (
            "An object does not expose the requested attribute.",
            [
                "Inspect the object's runtime type and available attributes.",
                "Check for misspelled names or unexpected None values.",
            ],
        ),
        "TypeError": (
            "An operation received an unexpected type or argument.",
            [
                "Check the types and values of the arguments.",
                "Verify the function signature and any None values.",
            ],
        ),
        "KeyError": (
            "A requested dictionary key or mapping key is missing.",
            [
                "Inspect the available keys and the input data shape.",
                "Use explicit validation or a safe lookup where appropriate.",
            ],
        ),
        "AssertionError": (
            "An assertion or test expectation failed.",
            [
                "Compare the expected value with the actual value.",
                "Check test fixtures, setup, and recent code changes.",
            ],
        ),
        "FileNotFoundError": (
            "A referenced file or directory could not be found.",
            [
                "Check the path, filename, and current working directory.",
                "Verify that the file exists in the execution environment.",
            ],
        ),
        "PermissionError": (
            "The process lacks permission for a file or resource operation.",
            [
                "Check file permissions and the identity running the process.",
                "Verify that the operation targets the intended resource.",
            ],
        ),
        "ConnectionError": (
            "A network or service connection failed.",
            [
                "Check service availability, network access, and the endpoint.",
                "Review connection settings and retry behavior.",
            ],
        ),
        "TimeoutError": (
            "An operation exceeded its allowed time.",
            [
                "Check service responsiveness and network latency.",
                "Review timeout settings before increasing them.",
            ],
        ),
    }

    if error_type == "UnknownError":
        summary = "The error could not be classified automatically."
        suggestions = [
            "Review the complete log and surrounding application context.",
            "Check the original error source for additional diagnostic details.",
        ]
    elif error_type in rules:
        summary, suggestions = rules[error_type]
    else:
        summary = f"An exception of type {error_type} was detected."
        suggestions = [
            "Inspect the exception message and the nearest relevant source frame.",
            "Reproduce the failure and verify the suspected cause before changing code.",
        ]

    return {
        "summary": summary,
        "suggestions": suggestions,
        "confidence": "low" if error_type == "UnknownError" else "medium",
        "confidence_note": (
            "These suggestions are heuristic and are not proof of root cause."
        ),
        "original_message": message,
    }


def analyze_text(text):
    """Analyze a log string and return a JSON-serializable report."""
    lines = text.splitlines()
    error = extract_error(lines)
    frames = extract_frames(lines)

    return {
        "tool": "StackTrace Copilot",
        "error": error,
        "source_frames": frames,
        "diagnosis": diagnose(error),
        "verification_steps": [
            "Inspect the source location and surrounding code, if available.",
            "Reproduce the failure with the same input and environment.",
            "Run the relevant test after any proposed fix.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(
        description="Analyze an error log or stack trace."
    )
    parser.add_argument(
        "--file",
        required=True,
        help="Path to a text file containing the error log.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the complete report as JSON.",
    )
    args = parser.parse_args()

    path = Path(args.file)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        parser.error(f"Could not read input file: {exc}")

    report = analyze_text(text)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"Error: {report['error']['message']}")
        print(f"Type: {report['error']['type']}")
        print(f"Diagnosis: {report['diagnosis']['summary']}")
        print(f"Confidence: {report['diagnosis']['confidence']}")

        if report["source_frames"]:
            print("\nSource locations:")
            for frame in report["source_frames"]:
                print(
                    f"  {frame['file']}:{frame['line']} "
                    f"({frame['function']})"
                )

        print("\nSuggested checks:")
        for suggestion in report["diagnosis"]["suggestions"]:
            print(f"  - {suggestion}")

        print("\nVerification:")
        for step in report["verification_steps"]:
            print(f"  - {step}")


if __name__ == "__main__":
    main()
