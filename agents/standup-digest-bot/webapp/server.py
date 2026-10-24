"""A tiny, dependency-free web UI for standup-digest-bot.

Why stdlib only
---------------
This server uses nothing but the Python standard library (http.server), so the
demo runs on a clean machine with no extra installs beyond the project's two
existing deps. It reuses the exact same agent pipeline as the CLI, so what you
see in the browser is the real thing, not a mock-up.

Run:
    python webapp/server.py            # then open http://localhost:8000
    python webapp/server.py --port 9000

Endpoints
---------
GET  /                -> the single-page UI (webapp/index.html)
GET  /api/fixtures    -> list of bundled real-data fixtures to pick from
POST /api/generate    -> run the agent; body: {source, user, date, fixture,
                                               provider, model}
                         returns: {activity, digest} (both already JSON-safe)
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
sys.path.insert(0, PROJECT_ROOT)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
except Exception:  # noqa: BLE001
    pass

from standup.agent import StandupAgent          # noqa: E402
from standup.fixtures import load_activity_log   # noqa: E402
from standup.github_tool import GitHubTool       # noqa: E402
from standup.llm import get_provider             # noqa: E402

FIXTURE_DIRS = [
    os.path.join(PROJECT_ROOT, "evals", "fixtures"),
    PROJECT_ROOT,  # picks up sample_activity.json
]


def list_fixtures() -> list[dict]:
    """Return selectable activity fixtures with a short label and event count."""
    found: list[dict] = []
    seen: set[str] = set()
    patterns = [
        os.path.join(PROJECT_ROOT, "sample_activity.json"),
        os.path.join(PROJECT_ROOT, "evals", "fixtures", "*.json"),
    ]
    for pattern in patterns:
        for path in sorted(glob.glob(pattern)):
            name = os.path.basename(path)
            if name in seen:
                continue
            seen.add(name)
            try:
                log = load_activity_log(path)
                rel = os.path.relpath(path, PROJECT_ROOT).replace("\\", "/")
                found.append(
                    {
                        "id": rel,
                        "label": f"{name}  ({len(log.events)} events, "
                        f"{log.username} @ {log.date})",
                        "username": log.username,
                        "date": log.date,
                    }
                )
            except Exception:  # noqa: BLE001 - skip unreadable files
                continue
    return found


def resolve_fixture_path(fixture_id: str) -> str:
    """Resolve a fixture id (relative path) safely under the project root."""
    candidate = os.path.normpath(os.path.join(PROJECT_ROOT, fixture_id))
    if not candidate.startswith(PROJECT_ROOT):
        raise ValueError("invalid fixture path")
    if not os.path.exists(candidate):
        raise FileNotFoundError(fixture_id)
    return candidate


def run_pipeline(body: dict) -> dict:
    """Execute the agent and return activity + digest as JSON-safe dicts."""
    source = body.get("source", "fixture")
    provider = body.get("provider") or None
    model = body.get("model") or None

    if source == "github":
        user = (body.get("user") or "").strip()
        date = (body.get("date") or "").strip()
        if not user or not date:
            raise ValueError("GitHub source requires both 'user' and 'date'.")
        tool = GitHubTool()
        log = tool.fetch_day(user, date)
    else:
        fixture = body.get("fixture")
        if not fixture:
            raise ValueError("Fixture source requires a 'fixture' selection.")
        log = load_activity_log(resolve_fixture_path(fixture))

    llm = get_provider(provider=provider, model=model)
    digest = StandupAgent(llm).generate(log)

    return {
        "provider": llm.name,
        "activity": log.to_dict(),
        "digest": digest.to_dict(),
    }


class Handler(BaseHTTPRequestHandler):
    # Quieter logging for the demo.
    def log_message(self, fmt, *args):  # noqa: D401
        sys.stderr.write("  [web] " + (fmt % args) + "\n")

    def _send(self, code: int, payload, content_type="application/json"):
        if isinstance(payload, (dict, list)):
            data = json.dumps(payload).encode("utf-8")
        elif isinstance(payload, str):
            data = payload.encode("utf-8")
        else:
            data = payload
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            with open(os.path.join(HERE, "index.html"), "r", encoding="utf-8") as fh:
                self._send(200, fh.read(), "text/html; charset=utf-8")
            return
        if self.path.startswith("/api/fixtures"):
            self._send(200, list_fixtures())
            return
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/api/generate":
            self._send(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length) or b"{}")
            result = run_pipeline(body)
            self._send(200, result)
        except (ValueError, FileNotFoundError) as exc:
            self._send(400, {"error": str(exc)})
        except Exception as exc:  # noqa: BLE001 - surface to the UI, keep serving
            self._send(500, {"error": f"{type(exc).__name__}: {exc}"})


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Demo web UI for standup-digest-bot.")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--host", default="127.0.0.1")
    args = p.parse_args(argv)

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}"
    print("=" * 60)
    print("  standup-digest-bot demo UI")
    print(f"  Open: {url}")
    print("  Press Ctrl+C to stop.")
    print("=" * 60)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
