"""CLI: python -m src.main overview --file data/sample_workbook.xlsx"""
from __future__ import annotations

import argparse
import json
import os

from dotenv import load_dotenv

from .clean import clean_sheet
from .ingest import load_google_sheet, load_xlsx
from .profiler import build_overview


def main() -> None:
    load_dotenv()
    p = argparse.ArgumentParser(description="MSME Business Health Agent")
    p.add_argument("mode", choices=["overview"], help="overview = first-upload high-level report")
    p.add_argument("--file", help="local .xlsx workbook")
    p.add_argument("--sheet-id", default=os.getenv("SHEET_ID"), help="Google Sheet ID")
    p.add_argument("--out", help="write JSON report to this path")
    args = p.parse_args()

    if args.file:
        raw = load_xlsx(args.file)
    elif args.sheet_id:
        raw = load_google_sheet(args.sheet_id, os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json"))
    else:
        p.error("provide --file or --sheet-id (or set SHEET_ID in .env)")

    sheets = {name: clean_sheet(df) for name, df in raw.items()}
    report = build_overview(sheets)
    text = json.dumps(report, indent=2, ensure_ascii=False)
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
    print(text)


if __name__ == "__main__":
    main()
