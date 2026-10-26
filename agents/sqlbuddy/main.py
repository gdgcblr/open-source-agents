
"""Interactive SQL assistant backed by the Google Gemini API."""

import logging
import os
from typing import Callable

from dotenv import load_dotenv
from google import genai
from google.genai import errors

load_dotenv()

logger = logging.getLogger(__name__)
API_KEY = os.getenv("GEMINI_API_KEY")
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
MISSING_KEY_MESSAGE = (
    "API key not configured. Add a valid GEMINI_API_KEY "
    "to your environment or local .env file."
)
PLACEHOLDER_KEYS = {"your_api_key_here", "your_gemini_api_key_here"}


def ask_gemini(prompt: str) -> str:
    """Send a non-empty prompt to Gemini and return its response or an error."""
    if not isinstance(prompt, str) or not prompt.strip():
        return "Please enter a non-empty prompt."

    api_key = API_KEY or os.getenv("GEMINI_API_KEY")
    if not api_key or api_key.strip().lower() in PLACEHOLDER_KEYS:
        return MISSING_KEY_MESSAGE

    model = (os.getenv("GEMINI_MODEL") or MODEL).strip()
    if not model:
        return "Model is not configured. Set GEMINI_MODEL to a model name."

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(model=model, contents=prompt)
        text = response.text
        return text.strip() if isinstance(text, str) and text.strip() else (
            "The model returned an empty response."
        )
    except errors.APIError as exc:
        logger.warning("Gemini API request failed: %s", exc)
        return f"Gemini API error: {exc}"
    except Exception:
        logger.exception("Unexpected failure while requesting a Gemini response")
        return "Unexpected error while contacting Gemini. Check the application logs."


def show_menu() -> None:
    """Display the available SQLBuddy actions."""
    print("\n===== SQLBuddy: AI SQL Assistant =====")
    print("1. Convert English to SQL")
    print("2. Explain an SQL query")
    print("3. Help with an SQL error")
    print("4. Exit")


def _read_non_empty(prompt: str, input_fn: Callable[[str], str]) -> str:
    """Read a required value, reporting empty input without making a request."""
    value = input_fn(prompt).strip()
    if not value:
        print("Input cannot be empty. Please try again.")
    return value


def main(input_fn: Callable[[str], str] = input) -> None:
    """Run the interactive menu; handle end-of-input cleanly for piped use."""
    print("Welcome to SQLBuddy!")

    while True:
        show_menu()
        try:
            choice = input_fn("Choose an option (1-4): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nInput closed. Goodbye!")
            return

        if choice == "1":
            question = _read_non_empty("Describe what you want to query: ", input_fn)
            if not question:
                continue
            schema = input_fn(
                "Optional table/schema details (press Enter to skip): "
            ).strip()
            prompt = f"""You are SQLBuddy, a careful SQL assistant.
Convert the user's request into a SQL query. Use the supplied schema when available.
If important details are missing, state your assumptions. Default to a read-only
SELECT query. Do not claim that the query has been executed. Return the SQL and
a brief explanation.

Schema:
{schema or "No schema supplied"}

User request:
{question}"""
            print("\n" + ask_gemini(prompt))

        elif choice == "2":
            query = _read_non_empty("Enter your SQL query: ", input_fn)
            if not query:
                continue
            prompt = f"""Explain this SQL query in beginner-friendly language.
Describe what it does and point out anything unclear. Do not execute the query.

SQL query:
{query}"""
            print("\n" + ask_gemini(prompt))

        elif choice == "3":
            query = input_fn("Enter the SQL query (if available): ").strip()
            error_message = _read_non_empty("Paste the SQL error message: ", input_fn)
            if not error_message:
                continue
            prompt = f"""Help a beginner understand this SQL error.
Explain likely causes and suggest a corrected query if possible. If information
is missing, say what needs checking. Do not claim the suggested query was tested
or executed.

SQL query:
{query or "Not supplied"}

Error:
{error_message}"""
            print("\n" + ask_gemini(prompt))

        elif choice == "4":
            print("Thanks for using SQLBuddy. Goodbye!")
            return

        else:
            print("Invalid choice. Please enter 1, 2, 3, or 4.")


if __name__ == "__main__":
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "WARNING").upper())
    main()
