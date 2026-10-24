
"""RepoGuide AI: generate an onboarding guide for a repository."""

import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

from main import inspect_repository


# Load environment variables from the .env file beside this script.
ENV_FILE = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=ENV_FILE)

GEMINI_MODEL = "gemini-3.5-flash-lite"
REQUEST_TIMEOUT_MS = 60_000


def format_local_report(report: dict) -> str:
    """Format local repository inspection results."""
    lines = ["Local repository checks:"]

    for item in report.get("results", []):
        status = item.get("status", "INFO")
        check = item.get("check", "Repository check")
        message = item.get("message", "")

        lines.append(f"- {status}: {check} — {message}")

    return "\n".join(lines)


def create_onboarding_guide(root: Path) -> str:
    """Inspect a repository and optionally generate an AI guide."""

    root = Path(root).expanduser().resolve()

    if not root.exists():
        raise FileNotFoundError(f"Repository does not exist: {root}")

    if not root.is_dir():
        raise NotADirectoryError(f"Not a directory: {root}")

    # Always perform local checks, even when AI is unavailable.
    report = inspect_repository(root)
    local_report = format_local_report(report)

    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        return (
            "AI mode is unavailable because GEMINI_API_KEY is not set.\n\n"
            f"{local_report}\n\n"
            "Add GEMINI_API_KEY to your local .env file to enable "
            "AI-generated guidance."
        )

    # Read the README when available to give the model useful context.
    readme_path = root / "README.md"

    if readme_path.is_file():
        readme = readme_path.read_text(
            encoding="utf-8",
            errors="replace",
        )[:12_000]
    else:
        readme = "README.md is missing."

    prompt = f"""
You are RepoGuide AI, a repository onboarding assistant.

Generate a practical onboarding guide using only the evidence provided.

Repository path:
{root}

Repository inspection results:
{json.dumps(report, indent=2, ensure_ascii=False)}

README content:
---
{readme}
---

Include these sections:
1. Project overview
2. Prerequisites
3. Setup and run instructions
4. Missing files or documentation
5. Suggested next steps for contributors

Important rules:
- Do not invent commands, dependencies, features, or project behavior.
- Clearly identify information that is not documented.
- Do not claim you executed commands or tests.
- Do not execute commands or modify repository files.
- Keep the guide clear, concise, and useful to a new contributor.
"""

    try:
        print("Sending request to Gemini...", flush=True)

        client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                timeout=REQUEST_TIMEOUT_MS,
            ),
        )

        interaction = client.interactions.create(
            model=GEMINI_MODEL,
            input=prompt,
        )

        guide = interaction.output_text

        if not guide or not guide.strip():
            raise RuntimeError(
                "The Gemini API returned an empty response."
            )

        print("Gemini response received.", flush=True)
        return guide.strip()

    except Exception as exc:
        error_type = type(exc).__name__
        error_message = str(exc)
        lowered_message = error_message.lower()

        if error_type == "APITimeoutError":
            reason = (
                "Gemini did not respond within 60 seconds. "
                "The service may be slow or temporarily overloaded. "
                "Please try again later."
            )

        elif (
            error_type == "InternalServerError"
            and (
                "503" in error_message
                or "high demand" in lowered_message
                or "service_unavailable" in lowered_message
            )
        ):
            reason = (
                "Gemini is temporarily unavailable or experiencing "
                "high demand. Please try again later."
            )

        else:
            reason = f"{error_type}: {error_message}"

        return (
            "AI generation is unavailable; showing local checks instead.\n"
            f"Reason: {reason}\n\n"
            f"{local_report}\n\n"
            "Your local repository checks completed successfully."
        )


def main() -> int:
    """Parse arguments and print the onboarding guide."""

    parser = argparse.ArgumentParser(
        description=(
            "Inspect a repository and generate an onboarding guide."
        )
    )

    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Path to the repository (default: current directory)",
    )

    args = parser.parse_args()

    try:
        guide = create_onboarding_guide(Path(args.path))

        print("\nRepoGuide AI — Onboarding Guide")
        print("=" * 40)
        print(guide)

        return 0

    except (FileNotFoundError, NotADirectoryError) as exc:
        parser.error(str(exc))

    except Exception as exc:
        print(
            f"Could not generate the onboarding guide: "
            f"{type(exc).__name__}: {exc}"
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
