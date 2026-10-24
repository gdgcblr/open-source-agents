"""Command-line entry point for the PDF-to-SurveyJS agent."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import warnings
from pathlib import Path

from dotenv import load_dotenv

from pdf_to_surveyjs_agent.tools import extract_pdf, validate_survey_json
from pdf_to_surveyjs_agent.workflow import (
    ConfigurationError,
    ConversionError,
    convert_pdf,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert a text-based PDF form into a reviewable SurveyJS JSON draft."
    )
    parser.add_argument("pdf", nargs="?", help="Path to the source PDF")
    parser.add_argument("-o", "--output", type=Path, help="Write JSON to this file")
    parser.add_argument(
        "--max-retries", type=int, default=None, help="Repair attempts after generation (0-2)"
    )
    parser.add_argument(
        "--extract-only",
        action="store_true",
        help="Print deterministic extraction metadata and text without calling a model",
    )
    parser.add_argument(
        "--validate-json",
        type=Path,
        help="Validate an existing SurveyJS JSON file without calling a model",
    )
    return parser


def main() -> int:
    load_dotenv()
    args = _parser().parse_args()

    if args.validate_json:
        try:
            result = validate_survey_json(args.validate_json.read_text(encoding="utf-8"))
        except OSError as exc:
            print(f"Error: could not read JSON file: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result["valid"] else 1

    if not args.pdf:
        print("Error: provide a PDF path or --validate-json.", file=sys.stderr)
        return 2

    if args.extract_only:
        result = extract_pdf(args.pdf).to_dict()
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result["ok"] else 1

    retries = args.max_retries
    if retries is None:
        import os

        raw_retries = os.getenv("PDF_SURVEY_MAX_RETRIES", "1")
        try:
            retries = int(raw_retries)
        except ValueError:
            print("Error: PDF_SURVEY_MAX_RETRIES must be an integer.", file=sys.stderr)
            return 2

    try:
        # ADK logs full internal tracebacks before surfacing API errors. The CLI
        # replaces those with concise, actionable messages below.
        logging.getLogger("google.adk.workflow._node_runner").setLevel(logging.CRITICAL)
        logging.getLogger("google.adk.runners").setLevel(logging.CRITICAL)
        warnings.filterwarnings(
            "ignore",
            message=r"\[EXPERIMENTAL\] feature FeatureName\.JSON_SCHEMA_FOR_FUNC_DECL.*",
        )
        result = asyncio.run(convert_pdf(args.pdf, max_retries=retries))
    except (ConfigurationError, ConversionError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    output = json.dumps(result.to_dict(), indent=2, ensure_ascii=False) + "\n"
    if args.output:
        try:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(output, encoding="utf-8")
        except OSError as exc:
            print(f"Error: could not write output: {exc}", file=sys.stderr)
            return 2
        print(f"Wrote SurveyJS draft to {args.output}")
    else:
        print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

