"""CLI for MSME Business Health Agent.

Usage:
  python -m src.main overview --file data/sample_workbook.xlsx
  python -m src.main process-xray --file data/sample_workbook.xlsx [--apa-json] [--out report.json]
  python -m src.main web [--port 8000]
"""
from __future__ import annotations

import argparse
import http.server
import json
import os
import socketserver
import webbrowser
from pathlib import Path

from dotenv import load_dotenv

from .clean import clean_sheet
from .ingest import load_google_sheet, load_xlsx
from .process_miner import detect_event_log, mine_process
from .profiler import build_overview


def run_web_server(port: int = 8000) -> None:
    web_dir = Path(__file__).resolve().parent.parent / "web"
    if not web_dir.exists() or not (web_dir / "index.html").exists():
        print(f"Error: Web directory or index.html not found at {web_dir}")
        return

    os.chdir(web_dir)
    handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer(("", port), handler) as httpd:
        url = f"http://localhost:{port}"
        print(f"Starting Process X-Ray Interactive Dashboard at {url}")
        print("Press Ctrl+C to stop the server.")
        try:
            webbrowser.open(url)
        except Exception:
            pass
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down web server.")


def main() -> None:
    load_dotenv()
    p = argparse.ArgumentParser(description="MSME Business Health Agent")
    p.add_argument(
        "mode",
        choices=["overview", "process-xray", "web"],
        help="overview = workbook health audit; process-xray = bottleneck & remediation X-ray; web = launch dashboard",
    )
    p.add_argument("--file", help="local .xlsx workbook")
    p.add_argument("--sheet-id", default=os.getenv("SHEET_ID"), help="Google Sheet ID")
    p.add_argument("--out", help="write JSON report to this path")
    p.add_argument(
        "--apa-json",
        action="store_true",
        help="in process-xray mode, output strictly the 6-key Agentic Process Automation JSON schema",
    )
    p.add_argument("--port", type=int, default=8000, help="port for web mode (default: 8000)")
    args = p.parse_args()

    if args.mode == "web":
        run_web_server(args.port)
        return

    if args.file:
        raw = load_xlsx(args.file)
    elif args.sheet_id:
        raw = load_google_sheet(args.sheet_id, os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json"))
    else:
        p.error("provide --file or --sheet-id (or set SHEET_ID in .env)")

    sheets = {name: clean_sheet(df) for name, df in raw.items()}

    if args.mode == "overview":
        report = build_overview(sheets)
        # Check for event log to include process mining block
        for sheet_name, df in sheets.items():
            cols = detect_event_log(df)
            if cols:
                report["process_mining"] = {
                    "sheet": sheet_name,
                    "analysis": mine_process(df, cols),
                }
                break

    elif args.mode == "process-xray":
        mining_results = {}
        for sheet_name, df in sheets.items():
            cols = detect_event_log(df)
            if cols:
                mining_results[sheet_name] = mine_process(df, cols)

        if not mining_results:
            report = {
                "error": "No event log sheet detected. A valid event log requires case ID, activity, and timestamp columns."
            }
        elif args.apa_json:
            # Output the strict 6-key APA JSON schema for the primary event log
            primary_sheet = next(iter(mining_results.keys()))
            apa_output = mining_results[primary_sheet].get("apa_output_json")
            report = apa_output if apa_output else {"error": "No bottleneck detected to generate APA output."}
        else:
            report = {
                "sheets_analyzed": list(mining_results.keys()),
                "process_mining": mining_results,
            }

    text = json.dumps(report, indent=2, ensure_ascii=False)
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
    print(text)


if __name__ == "__main__":
    main()
