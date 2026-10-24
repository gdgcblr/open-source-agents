"""Loopback-only web dashboard for the offline ReproCapsule demo."""

from __future__ import annotations

import contextlib
import io
import json
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from urllib.parse import urlparse

from .cli import demo
from .tools import list_files

HOST = "127.0.0.1"
PORT = 8765
FIXTURE = Path(__file__).resolve().parents[2] / "examples" / "timeout-bug-repo"


class DashboardHandler(BaseHTTPRequestHandler):
    """Serve one static page and a tiny, local-only demo API."""

    server_version = "ReproCapsuleDashboard/0.1"

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        route = urlparse(self.path).path
        if route == "/":
            html = files("repro_capsule").joinpath("ui/index.html").read_bytes()
            self._send(200, html, "text/html; charset=utf-8")
            return
        if route == "/api/overview":
            try:
                payload = {
                    "fixture": "Timeout parser regression",
                    "files": list_files(FIXTURE),
                    "repo": FIXTURE.name,
                    "guardrails": [
                        "Model has no shell or test execution tool",
                        "The offline demo runs only an agent-owned fixture",
                        "Actual repository tests require explicit CLI authorization",
                    ],
                }
                body = json.dumps(payload).encode("utf-8")
                self._send(200, body, "application/json; charset=utf-8")
            except (OSError, ValueError) as exc:
                self._send(500, json.dumps({"error": str(exc)}).encode(), "application/json; charset=utf-8")
            return
        self._send(404, b"Not found", "text/plain; charset=utf-8")

    def do_POST(self) -> None:  # noqa: N802
        if urlparse(self.path).path != "/api/demo":
            self._send(404, b"Not found", "text/plain; charset=utf-8")
            return
        origin = self.headers.get("Origin", "")
        if origin and origin not in {f"http://{HOST}:{PORT}", f"http://localhost:{PORT}"}:
            self._send(403, b"Origin rejected", "text/plain; charset=utf-8")
            return
        output = io.StringIO()
        try:
            with contextlib.redirect_stdout(output):
                exit_code = demo()
            capsule = json.loads(output.getvalue())
            execution = capsule["execution"]
            payload = {
                "exit_code": exit_code,
                "capsule": capsule,
                "summary": {
                    "status": execution["status"],
                    "test_exit_code": execution["exit_code"],
                    "mode": execution["mode"],
                    "command": execution["command"],
                    "stdout": execution["stdout"],
                    "stderr": execution["stderr"],
                },
            }
            self._send(200, json.dumps(payload).encode("utf-8"), "application/json; charset=utf-8")
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
            self._send(500, json.dumps({"error": str(exc)}).encode(), "application/json; charset=utf-8")

    def log_message(self, format: str, *args: object) -> None:
        print(f"[dashboard] {format % args}")


def serve() -> int:
    """Start the dashboard on loopback and open it in the default browser."""
    try:
        with ThreadingHTTPServer((HOST, PORT), DashboardHandler) as server:
            url = f"http://{HOST}:{PORT}"
            print(f"ReproCapsule dashboard: {url}")
            print("This server listens only on this computer. Press Ctrl+C to stop.")
            webbrowser.open(url)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                print("\nDashboard stopped.")
    except OSError as exc:
        print(f"Could not start dashboard on {HOST}:{PORT}: {exc}")
        return 1
    return 0
