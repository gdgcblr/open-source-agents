"""A tiny support bot running as an HTTP service: the agent under test for murphy's `http` target.

No MCP and no framework: it shows that any agent behind an HTTP endpoint can be stress-tested.
It opens a support ticket when a customer reports a problem. The bug: in the default (naive)
mode it opens a NEW ticket every time the customer repeats the problem.

  POST /chat               {"session_id", "message"} -> {"reply"}     (?mode=fixed dedupes tickets)
  GET  /admin/tickets      ?email=...&since=<unix ts> -> {"count", "tickets"}

Run:  python examples/http_support_bot/server.py [--port 8010]
"""

from __future__ import annotations

import argparse
import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
PROBLEM = re.compile(r"(?i)\b(broken|not working|doesn'?t work|error|crash\w*|fails?|failing|stuck|can'?t log ?in)\b")


class Desk:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.sessions: dict[str, dict] = {}
        self.tickets: list[dict] = []

    def chat(self, session_id: str, message: str, fixed: bool) -> str:
        with self.lock:
            s = self.sessions.setdefault(session_id, {"email": None, "problem": None, "ticket": None})
            if m := EMAIL.search(message):
                s["email"] = m.group(0).lower()
            if PROBLEM.search(message):
                s["problem"] = message.strip()
            if not s["problem"]:
                return "Hi! What seems to be the problem?"
            if not s["email"]:
                return "Sorry about that. What's the email on your account?"
            if PROBLEM.search(message) or s["ticket"] is None:
                if fixed and s["ticket"]:
                    return f"You're all set, ticket {s['ticket']} is already open and our team is on it."
                ticket = f"T-{len(self.tickets) + 1}"
                self.tickets.append({"id": ticket, "email": s["email"], "problem": s["problem"], "ts": time.time()})
                s["ticket"] = ticket
                return f"I've opened ticket {ticket} for {s['email']}. Our team will reply within 24 hours."
            return "Anything else I can help with?"

    def find(self, email: str, since: float) -> list[dict]:
        with self.lock:
            return [t for t in self.tickets if t["email"] == email.lower() and t["ts"] >= since]


def make_handler(desk: Desk):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, body: dict) -> None:
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            url = urlparse(self.path)
            if url.path != "/chat":
                return self._send(404, {"error": "not found"})
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            fixed = parse_qs(url.query).get("mode") == ["fixed"]
            self._send(200, {"reply": desk.chat(str(body.get("session_id", "")), str(body.get("message", "")), fixed)})

        def do_GET(self):
            url = urlparse(self.path)
            if url.path != "/admin/tickets":
                return self._send(404, {"error": "not found"})
            q = parse_qs(url.query)
            tickets = desk.find(q.get("email", [""])[0], float(q.get("since", ["0"])[0]))
            self._send(200, {"count": len(tickets), "tickets": tickets})

        def log_message(self, *args):
            pass

    return Handler


def serve(port: int = 8010) -> ThreadingHTTPServer:
    return ThreadingHTTPServer(("127.0.0.1", port), make_handler(Desk()))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8010)
    server = serve(parser.parse_args().port)
    print(f"support bot on http://127.0.0.1:{server.server_port}/chat (naive) and /chat?mode=fixed")
    server.serve_forever()
