"""Intentionally inconsistent Notes API, for a local ClaimCheck demo only."""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/health":
            status, body = 200, {"status": "ok"}
        elif self.path == "/notes":
            status, body = 200, [{"id": "not-an-integer", "title": "A deliberately broken note"}]
        else:
            status, body = 404, {"error": "not found"}
        encoded = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args: object) -> None:
        pass


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=9000)
    parser.add_argument("--ready-file", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        print("notes demo ready")
        return
    with ThreadingHTTPServer(("127.0.0.1", args.port), Handler) as server:
        if args.ready_file:
            args.ready_file.write_text(json.dumps({"port": server.server_port}))
        server.serve_forever()


if __name__ == "__main__":
    main()
