"""Minimal Streamable HTTP MCP server used for tests and demos (standard library only).

Run manually:  python tests/fake_mcp_http_server.py --mode poisoned --port 8765
Then scan:     python -m mcp_poison_scan scan --url http://127.0.0.1:8765/mcp
"""

import argparse
import json
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from fake_mcp_server import PAGE_SIZE, load_tools


def make_handler(tools, response_format="json", token=None):
    sessions = set()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # keep test output quiet
            pass

        def _reply(self, status, body=None, headers=None):
            self.send_response(status)
            for name, value in (headers or {}).items():
                self.send_header(name, value)
            if body is None:
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if response_format == "sse":
                # An unrelated notification first, to check that clients skip it.
                note = {"jsonrpc": "2.0", "method": "notifications/message", "params": {"data": "hi"}}
                payload = f"event: message\ndata: {json.dumps(note)}\n\nevent: message\ndata: {json.dumps(body)}\n\n"
                content_type = "text/event-stream"
            else:
                payload = json.dumps(body)
                content_type = "application/json"
            data = payload.encode("utf-8")
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            if self.path == "/redirect":
                return self._reply(307, headers={"Location": "http://example.invalid/mcp"})
            if self.path != "/mcp":
                return self._reply(404)
            if token and self.headers.get("Authorization") != f"Bearer {token}":
                return self._reply(401, headers={"WWW-Authenticate": 'Bearer realm="fake"'})
            request = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            if "id" not in request:
                return self._reply(202)
            method = request.get("method")
            if method == "initialize":
                session = uuid.uuid4().hex
                sessions.add(session)
                result = {
                    "protocolVersion": request["params"].get("protocolVersion"),
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "fake-mcp-http-server", "version": "1.0.0"},
                }
                return self._reply(200, {"jsonrpc": "2.0", "id": request["id"], "result": result},
                                   {"Mcp-Session-Id": session})
            if self.headers.get("Mcp-Session-Id") not in sessions:
                return self._reply(400, {"jsonrpc": "2.0", "id": request["id"],
                                         "error": {"code": -32000, "message": "missing session"}})
            if method == "tools/list":
                start = int((request.get("params") or {}).get("cursor") or 0)
                result = {"tools": tools[start:start + PAGE_SIZE]}
                if start + PAGE_SIZE < len(tools):
                    result["nextCursor"] = str(start + PAGE_SIZE)
                return self._reply(200, {"jsonrpc": "2.0", "id": request["id"], "result": result})
            return self._reply(200, {"jsonrpc": "2.0", "id": request["id"],
                                     "error": {"code": -32601, "message": f"Method not found: {method}"}})

        def do_DELETE(self):
            sessions.discard(self.headers.get("Mcp-Session-Id"))
            self._reply(200)

    return Handler


def start(mode="benign", response_format="json", token=None, port=0):
    """Start the server in a background thread. Returns (server, base_url)."""
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(load_tools(mode), response_format, token))
    threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("benign", "poisoned", "rugpull"), default="benign")
    parser.add_argument("--format", choices=("json", "sse"), default="json")
    parser.add_argument("--token", help="require 'Authorization: Bearer <token>'")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server, url = start(args.mode, args.format, args.token, args.port)
    print(f"Serving {args.mode} tools at {url}/mcp (Ctrl+C to stop)")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        server.shutdown()
