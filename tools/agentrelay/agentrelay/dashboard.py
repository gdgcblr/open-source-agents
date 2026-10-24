"""Lightweight local web server for the interactive AgentRelay Dashboard."""

from __future__ import annotations

import http.server
import json
import socketserver
import webbrowser
from pathlib import Path
from typing import Optional

from agentrelay.code_review import run_deterministic_review
from agentrelay.correlation import correlate_review_and_incident
from agentrelay.evaluator import run_eval_suite
from agentrelay.incident_investigator import run_incident_investigation


class DashboardHandler(http.server.SimpleHTTPRequestHandler):
    """HTTP request handler providing dashboard HTML and local investigation APIs."""

    def do_GET(self) -> None:
        if self.path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return

        if self.path in ("/", "/index.html", "/dashboard"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()

            # Load the dashboard HTML artifact or bundled template
            artifact_path = Path(__file__).resolve().parent / "dashboard.html"
            if not artifact_path.exists():
                # Check brain artifact directory
                brain_path = Path("/Users/mac/.gemini/antigravity/brain/4d56ee57-4ec3-472c-8795-4717cdde7414/dashboard.html")
                if brain_path.exists():
                    artifact_path = brain_path

            if artifact_path.exists():
                self.wfile.write(artifact_path.read_bytes())
            else:
                self.wfile.write(b"<h1>AgentRelay Dashboard</h1><p>Dashboard HTML not found.</p>")
            return

        super().do_GET()

    def do_POST(self) -> None:
        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length)

        try:
            payload = json.loads(post_data.decode("utf-8")) if post_data else {}
        except Exception:
            payload = {}

        if self.path == "/api/review":
            diff_text = payload.get("diff", "")
            commit_id = payload.get("commit_id")
            service = payload.get("service")
            report, ev_store = run_deterministic_review(diff_text, commit_id=commit_id, service=service)
            self._send_json({"report": report.to_dict(), "evidence": ev_store.to_list()})
            return

        elif self.path == "/api/investigate":
            incident_data = payload.get("incident", {})
            report, ev_store = run_incident_investigation(incident_data)
            self._send_json({"report": report.to_dict(), "evidence": ev_store.to_list()})
            return

        elif self.path == "/api/correlate":
            review_rep = payload.get("review_report", {})
            incident_data = payload.get("incident", {})
            corr_rep = correlate_review_and_incident(review_rep, incident_data)
            self._send_json(corr_rep.to_dict())
            return

        elif self.path == "/api/evaluate":
            cases_path = Path(__file__).resolve().parent.parent / "evals" / "test_cases.json"
            if cases_path.exists():
                with open(cases_path, encoding="utf-8") as f:
                    cases = json.load(f)
                summary = run_eval_suite(cases)
                self._send_json(summary.to_dict())
            else:
                self._send_json({"error": "test_cases.json not found"}, status=404)
            return

        self.send_response(404)
        self.end_headers()

    def _send_json(self, data: dict, status: int = 200) -> None:
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def run_dashboard_server(host: str = "127.0.0.1", port: int = 8080, open_browser: bool = True) -> None:
    """Start local web server on specified port."""
    server_address = (host, port)
    # Allow port reuse
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(server_address, DashboardHandler) as httpd:
        url = f"http://{host}:{port}/"
        print("=" * 70)
        print(" AgentRelay — Interactive Investigation Dashboard Server")
        print("=" * 70)
        print(f" Local URL: {url}")
        print(" Press Ctrl+C to stop the dashboard server.")
        print("=" * 70)
        if open_browser:
            try:
                webbrowser.open(url)
            except Exception:
                pass
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down dashboard server.")
            httpd.shutdown()
