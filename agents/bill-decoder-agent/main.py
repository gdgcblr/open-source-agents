"""
bill-decoder-agent
Explains any Indian utility bill (electricity, water, mobile, broadband)
in simple language and flags charges that look unusual.

Usage:
    python main.py path/to/bill.jpg
    python main.py path/to/bill.pdf --lang kannada
"""

import argparse
import datetime
import mimetypes
import os
import sys

from dotenv import load_dotenv
from google import genai
from google.genai import errors, types

from bill_terms import TERM_NOTES
from guardrails import INJECTION_RULE, check_file, date_rule

PROMPT = """You are a friendly assistant that explains Indian utility bills
(electricity, water, gas, mobile, broadband) to ordinary people.

Look at the attached bill and reply in {language}, using simple words.
Use exactly these sections:

1. BILL SUMMARY
   - Type of bill and provider
   - Billing period
   - Total amount to pay and the due date

2. CHARGES EXPLAINED
   - List every charge on the bill with its amount. For each one, explain in
     simple words what it means, why the company charges it, and whether it can
     be reduced or avoided.

3. RED FLAGS
   - Point out anything unusual: late fees, arrears from earlier bills,
     sudden jump in usage compared with previous months (if shown),
     estimated (not actual) meter readings, unknown or extra charges,
     or calculation mistakes.
   - If nothing looks wrong, say "No red flags found."

4. MONEY-SAVING TIPS
   - Give 2 or 3 practical tips specific to this type of bill.

Rules:
- Only use information that is actually printed on the bill.
- If something is unclear or unreadable, say so instead of guessing.
- If the file is not a bill, say so and stop.
""" + TERM_NOTES + INJECTION_RULE


def decode_bill(file_path: str, language: str) -> str:
    """Send the bill to Gemini and return the explanation text."""
    mime_type, _ = mimetypes.guess_type(file_path)
    problem = check_file(mime_type, os.path.getsize(file_path))
    if problem:
        raise ValueError(problem)

    with open(file_path, "rb") as f:
        file_bytes = f.read()

    return decode_bill_bytes(file_bytes, mime_type, language)


def model_list() -> list[str]:
    """Preferred model first, then backups. Each model has its own free-tier quota."""
    preferred = os.getenv("MODEL_NAME", "gemini-3.5-flash")
    backups = ["gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]
    return [preferred] + [m for m in backups if m != preferred]


def generate_with_fallback(contents: list, config: types.GenerateContentConfig | None = None):
    """
    Call Gemini, moving to the next model when one is busy (503) or out of quota (429).
    Raises the last error if every model fails.
    """
    client = genai.Client(
        api_key=os.getenv("GEMINI_API_KEY"),
        # Fail fast instead of the SDK's long internal retries, so we can switch models.
        http_options=types.HttpOptions(timeout=90_000, retry_options=types.HttpRetryOptions(attempts=1)),
    )
    last_error = None
    for model in model_list():
        try:
            return client.models.generate_content(model=model, contents=contents, config=config)
        except errors.APIError as e:
            if e.code not in (429, 503):
                raise
            last_error = e
    raise last_error


def decode_bill_bytes(file_bytes: bytes, mime_type: str, language: str) -> str:
    """Send raw bill bytes (e.g. from a web upload) to Gemini."""
    response = generate_with_fallback([
        types.Part.from_bytes(data=file_bytes, mime_type=mime_type),
        PROMPT.format(language=language) + date_rule(datetime.date.today()),
    ])
    return response.text


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Explain an Indian utility bill in simple language."
    )
    parser.add_argument("bill", help="Path to the bill photo or PDF")
    parser.add_argument(
        "--lang",
        default="English",
        help="Language for the explanation, e.g. English, Kannada, Hindi (default: English)",
    )
    args = parser.parse_args()

    load_dotenv()
    if not os.getenv("GEMINI_API_KEY"):
        sys.exit("Error: GEMINI_API_KEY is not set. Copy .env.example to .env and add your key.")

    if not os.path.isfile(args.bill):
        sys.exit(f"Error: file not found: {args.bill}")

    print(f"Decoding {args.bill} ...\n")
    try:
        print(decode_bill(args.bill, args.lang))
    except ValueError as e:
        sys.exit(f"Error: {e}")
    except errors.APIError as e:
        if e.code == 503:
            sys.exit("Error: the Gemini model is busy right now. Wait a minute and try again.")
        if e.code == 429:
            sys.exit("Error: the free Gemini quota is used up for today on all models. Try again later.")
        sys.exit(f"Error: something went wrong with the Gemini API (code {e.code}). Please try again later.")


if __name__ == "__main__":
    main()
