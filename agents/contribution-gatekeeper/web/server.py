"""Local web console for the gatekeeper.

    python web/server.py [port]     # http://127.0.0.1:8765

Serves the console (web/index.html) and a small JSON API:

    GET  /api/health   -> {"llm": bool, "docker": bool}
    POST /api/review   {"target": "<PR URL | path>", "llm": bool, "run_setup": bool, "project": str|null}
                       -> the report JSON (report.to_json + review_markdown, notes)

Binds to 127.0.0.1 only: it runs git and (optionally) Docker on this machine.
Without the server, the console still works offline on the bundled demo reports.
"""

from __future__ import annotations

import json
import sys
import threading
import traceback
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

try:
    from dotenv import load_dotenv

    load_dotenv(HERE.parent / ".env")
except ImportError:
    pass

from contribution_gatekeeper import agent as gk  # noqa: E402
from contribution_gatekeeper import cli  # noqa: E402
from contribution_gatekeeper import report as render  # noqa: E402
from contribution_gatekeeper import sandbox  # noqa: E402

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
_one_at_a_time = threading.Lock()  # the pipeline keeps per-run state in module globals


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(HERE), **kw)

    def _json(self, code: int, obj) -> None:
        body = render.dump(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/health":
            return self._json(200, {"llm": gk.llm_available(), "docker": sandbox.available()})
        return super().do_GET()

    def do_POST(self):
        if self.path != "/api/review":
            return self._json(404, {"error": "not found"})
        try:
            req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            target = str(req.get("target", "")).strip()
            if not target:
                return self._json(400, {"error": "target is required"})
            with _one_at_a_time:
                rep = cli.review(target, use_llm=bool(req.get("llm")) and gk.llm_available(),
                                 run_setup=bool(req.get("run_setup")), project=req.get("project") or None,
                                 quiet=True)
            out = render.to_json(rep)
            out.update(review_markdown=rep.review_markdown, notes=rep.notes,
                       changed_files=rep.submission.changed_files)
            return self._json(200, out)
        except Exception as e:  # surface the reason in the UI instead of a bare 500
            traceback.print_exc()
            return self._json(500, {"error": f"{type(e).__name__}: {e}"})

    def log_message(self, fmt, *args):
        if "/api/" in (args[0] if args else ""):
            super().log_message(fmt, *args)


def main() -> None:
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Gatekeeper console: http://127.0.0.1:{PORT}  (Ctrl+C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
