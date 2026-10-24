"""Local web UI: serves web/ and a small JSON + server-sent events API around run_check.

    python -m firstrun.web            then open http://127.0.0.1:8765

Starting a check makes this machine run commands from someone's README, so the server only
listens on loopback, checks the Host header (DNS rebinding) and only accepts JSON POSTs from
its own origin (a random website cannot start a run through your browser).
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import re
import sys
import threading
import time
import traceback
import webbrowser
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import unquote, urlsplit

from . import __version__, agent, llm, sandbox
from .cli import load_own_dotenv, parse_env_text
from .project import read_text
from .report import write_events

ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT / "web"
EXAMPLES_DIR = ROOT / "examples"

DOWNLOADS = {
    "report.md": "text/markdown; charset=utf-8",
    "report.json": "application/json",
    "comment.md": "text/markdown; charset=utf-8",
    "fix.patch": "text/x-diff; charset=utf-8",
    "verified-setup.sh": "text/x-shellscript; charset=utf-8",
    "events.jsonl": "application/x-ndjson",
}
LOG_NAME = re.compile(r"^logs/([A-Za-z0-9][A-Za-z0-9._-]*\.log)$")
RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,120}$")
ENV_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
IMAGE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/:@-]{0,200}$")
MIME = {
    ".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8", ".mjs": "text/javascript; charset=utf-8",
    ".json": "application/json", ".map": "application/json", ".svg": "image/svg+xml",
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
    ".gif": "image/gif", ".ico": "image/x-icon", ".woff2": "font/woff2", ".woff": "font/woff",
    ".ttf": "font/ttf", ".txt": "text/plain; charset=utf-8", ".md": "text/markdown; charset=utf-8",
}
MAX_BODY = 64 * 1024
PLACEHOLDER_PAGE = (
    "<!doctype html><meta charset=utf-8><title>FirstRun</title>"
    "<p>The web UI files are missing (expected web/index.html). The API is up at /api/status.</p>"
)


class BadRequest(ValueError):
    pass


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "project"


def _bool(value, name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str) and value.strip().lower() in ("true", "1", "yes", "on"):
        return True
    if isinstance(value, str) and value.strip().lower() in ("false", "0", "no", "off", ""):
        return False
    raise BadRequest(f"{name} must be true or false")


def _int(value, name: str, lo: int, hi: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise BadRequest(f"{name} must be a whole number") from None
    if isinstance(value, float) and value != number:
        raise BadRequest(f"{name} must be a whole number")
    if not lo <= number <= hi:
        raise BadRequest(f"{name} must be between {lo} and {hi}")
    return number


def _is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host.strip("[]")).is_loopback
    except ValueError:
        return False


def resolve_target_path(target: str) -> str:
    """Example paths from the UI are relative to the FirstRun folder, not to wherever we run."""
    if "://" in target or target.startswith("git@") or target.startswith("github.com/"):
        return target
    p = Path(target).expanduser()
    if not p.is_absolute() and (ROOT / p).exists():
        return str((ROOT / p).resolve())
    return str(p.resolve()) if p.exists() else target


def parse_run_request(body: dict, out_dir: Path) -> tuple[str, Optional[str], agent.Settings]:
    if not isinstance(body, dict):
        raise BadRequest("send a JSON object")
    target = body.get("target")
    if not isinstance(target, str) or not target.strip():
        raise BadRequest("target is required (a folder or a GitHub URL)")
    if len(target) > 2000:
        raise BadRequest("target is too long")
    subdir = body.get("subdir") or None
    if subdir is not None and (not isinstance(subdir, str) or len(subdir) > 500):
        raise BadRequest("subdir must be a short relative path")
    if subdir is not None:
        subdir = subdir.strip().strip("/") or None

    defaults = agent.Settings()
    kind = body.get("sandbox", defaults.sandbox)
    if kind not in ("docker", "local"):
        raise BadRequest("sandbox must be docker or local")
    image = body.get("image") or defaults.image
    if not isinstance(image, str) or not IMAGE.match(image):
        raise BadRequest("image must be a Docker image name like python:3.12-slim")
    offline = _bool(body.get("offline", defaults.offline), "offline")
    rounds = _int(body.get("max_rounds", defaults.max_rounds), "max_rounds", 0, 5)
    repair = _bool(body.get("repair", defaults.repair), "repair") and rounds > 0
    watch = _int(body.get("watch_seconds", defaults.watch_seconds), "watch_seconds", 1, 300)
    timeout = _int(body.get("timeout", defaults.timeout), "timeout", 30, 3600)

    secrets = body.get("secrets") or ""
    if not isinstance(secrets, str) or len(secrets) > 20_000:
        raise BadRequest("secrets must be KEY=VALUE lines")
    env = parse_env_text(secrets)
    for key in env:
        if not ENV_KEY.match(key):
            # never echo the line back, it may hold the secret itself
            raise BadRequest("every secrets line must look like NAME=value")

    settings = agent.Settings(
        sandbox=kind, image=image, offline=offline, max_rounds=max(1, rounds), repair=repair,
        timeout=timeout, watch_seconds=watch, env=env, out_dir=out_dir,
    )
    resolved = resolve_target_path(target.strip())
    remote = "://" in resolved or resolved.startswith(("git@", "github.com/")) or resolved.endswith(".git")
    if not remote and not Path(resolved).expanduser().is_dir():
        # say it on the form instead of recording a run that could never start
        raise BadRequest(f"There is no folder at {target.strip()}. Use a path on this machine "
                         "(relative to the FirstRun folder works) or a github.com link.")
    return resolved, subdir, settings


def _first_sentence(text: str) -> str:
    text = " ".join(text.split())
    m = re.match(r"(.+?[.!?])(\s|$)", text)
    return m.group(1) if m else text


def _plain(md: str) -> str:
    md = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", md)
    return " ".join(md.replace("`", "").replace("**", "").split())


def list_examples(examples_dir: Path = EXAMPLES_DIR) -> list[dict]:
    if not examples_dir.is_dir():
        return []
    notes: dict[str, dict] = {}
    index = read_text(examples_dir / "README.md") or ""
    for line in index.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        m = re.search(r"`([^`]+)`", cells[0]) if len(cells) >= 3 else None
        if m:
            expected = _plain(cells[2])
            verdict = re.match(r"\*\*([a-z]+)", cells[2])
            notes[m.group(1)] = {"broken": _plain(cells[1]), "expected": expected,
                                 "expected_verdict": verdict.group(1) if verdict else None}
    out = []
    for folder in sorted(p for p in examples_dir.iterdir() if p.is_dir() and not p.name.startswith(".")):
        readme = read_text(folder / "README.md") or ""
        summary = ""
        for line in readme.splitlines():
            if line.startswith(">"):
                summary = _first_sentence(line.lstrip("> ").strip())
                break
        if not summary:
            body = [ln for ln in readme.splitlines() if ln.strip() and not ln.startswith(("#", "-", "|", "`"))]
            summary = _first_sentence(body[0]) if body else ""
        item = {"name": folder.name, "path": f"examples/{folder.name}", "summary": summary}
        item.update(notes.get(folder.name, {}))
        out.append(item)
    return out


class LiveRun:
    """Events of a run in progress, shared between the worker thread and SSE readers."""

    def __init__(self, run_id: str, run_dir: Path, target: str, subdir: Optional[str]):
        self.id, self.run_dir, self.target, self.subdir = run_id, run_dir, target, subdir
        self.started_at = datetime.now().astimezone().isoformat(timespec="seconds")
        self.t0 = time.time()
        self.events: list[dict] = []
        self.cond = threading.Condition()
        self.done = False  # worker finished
        self.saw_done = False  # the agent sent its done event, so report.json is on disk

    def add(self, kind: str, message: str, data: Optional[dict] = None) -> None:
        # seq matches what agent._Recorder writes to events.jsonl: one counter, same order
        with self.cond:
            self.events.append({"seq": len(self.events), "t": round(time.time() - self.t0, 3),
                                "kind": kind, "message": message, "data": data})
            if kind == "done":
                self.saw_done = True
            self.cond.notify_all()

    def finish(self) -> None:
        with self.cond:
            self.done = True
            self.cond.notify_all()

    def wait_from(self, seq: int, timeout: float) -> tuple[list[dict], bool]:
        with self.cond:
            self.cond.wait_for(lambda: len(self.events) > seq or self.done, timeout=timeout)
            return list(self.events[seq:]), self.done

    def summary(self) -> dict:
        name = Path(self.subdir or self.target.rstrip("/")).name or self.target
        return {"id": self.id, "project": name, "source": self.target, "verdict": None,
                "headline": "Running", "started_at": self.started_at, "metrics": {}, "state": "running"}


class App:
    def __init__(self, out_dir: Path, web_dir: Path = WEB_DIR, examples_dir: Path = EXAMPLES_DIR,
                 allow_remote: bool = False, heartbeat: float = 15.0, quiet: bool = False):
        self.out_dir, self.web_dir, self.examples_dir = Path(out_dir), Path(web_dir), Path(examples_dir)
        self.allow_remote, self.heartbeat, self.quiet = allow_remote, heartbeat, quiet
        self.lock = threading.Lock()
        self.active: Optional[LiveRun] = None
        self.live: dict[str, LiveRun] = {}
        self._status_cache: tuple[float, dict] = (0.0, {})

    # status --------------------------------------------------------------

    def environment(self) -> dict:
        now = time.time()
        stamp, cached = self._status_cache
        if cached and now - stamp < 10:
            return cached
        try:
            ok, detail = sandbox.DockerSandbox().available()
        except Exception as exc:  # a broken docker CLI should not take the page down
            ok, detail = False, str(exc)
        model = None
        try:
            client = llm.get_llm()
        except llm.LLMError:
            client = None
        if client is not None:
            model = getattr(client, "model", None) or client.name
        env = {"docker": {"ok": ok, "detail": detail or "docker is running"},
               "gemini": {"ok": client is not None, "model": model,
                          "label": "Groq" if client is not None and client.name.startswith("groq") else "Gemini"}}
        self._status_cache = (now, env)
        return env

    def status(self) -> dict:
        d = agent.Settings()
        with self.lock:
            active = self.active.id if self.active else None
        return {
            "version": __version__,
            **self.environment(),
            "examples": list_examples(self.examples_dir),
            "defaults": {"target": "examples/quote-of-the-day", "sandbox": d.sandbox, "image": d.image,
                         "offline": d.offline, "max_rounds": d.max_rounds, "repair": d.repair,
                         "watch_seconds": d.watch_seconds, "timeout": d.timeout},
            "busy": active is not None,
            "active_run": active,
        }

    # runs ----------------------------------------------------------------

    def new_run_id(self, target: str, subdir: Optional[str]) -> str:
        name = Path(subdir or target.rstrip("/").removesuffix(".git")).name or "project"
        base = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{_slug(name)}"
        run_id, n = base, 2
        while (self.out_dir / run_id).exists() or run_id in self.live:
            run_id, n = f"{base}-{n}", n + 1
        return run_id

    def start(self, target: str, subdir: Optional[str], settings: agent.Settings) -> Optional[LiveRun]:
        with self.lock:
            if self.active is not None:
                return None
            run_id = self.new_run_id(target, subdir)
            live = LiveRun(run_id, self.out_dir / run_id, target, subdir)
            self.active = live
            self.live[run_id] = live
        threading.Thread(target=self._work, args=(live, settings), name=f"firstrun-{run_id}", daemon=True).start()
        return live

    def _work(self, live: LiveRun, settings: agent.Settings) -> None:
        try:
            agent.run_check(live.target, settings, subdir=live.subdir, on_event=live.add, run_dir=live.run_dir)
        except Exception as exc:
            # only the exception type and message, the settings (with secrets) never get printed
            print(f"firstrun web: run {live.id} crashed: {type(exc).__name__}: {exc}", file=sys.stderr)
            traceback.print_exc(limit=3)
            live.add("warn", f"FirstRun crashed: {exc}", None)
            live.add("done", f"FirstRun crashed: {exc}", {"verdict": "error", "run_dir": str(live.run_dir)})
            try:
                write_events(live.events, live.run_dir)
            except OSError:
                pass
        finally:
            if not any(ev["kind"] == "done" for ev in live.events[-3:]):
                live.add("done", "Run ended", {"verdict": "error", "run_dir": str(live.run_dir)})
            live.finish()
            with self.lock:
                if self.active is live:
                    self.active = None

    def run_dir(self, run_id: str) -> Optional[Path]:
        if not RUN_ID.match(run_id):
            return None
        path = (self.out_dir / run_id)
        try:
            path.resolve().relative_to(self.out_dir.resolve())
        except ValueError:
            return None
        return path

    def load_report(self, run_id: str) -> Optional[dict]:
        path = self.run_dir(run_id)
        if path is None:
            return None
        text = read_text(path / "report.json", limit=20_000_000)
        if text is None:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

    def get_run(self, run_id: str) -> Optional[dict]:
        live = self.live.get(run_id)
        if live is not None and not (live.done or live.saw_done):
            return {"id": run_id, "state": "running", "report": None}
        path = self.run_dir(run_id)
        if path is None or not (path.is_dir() and ((path / "report.json").exists() or (path / "events.jsonl").exists())):
            return None
        return {"id": run_id, "state": "done", "report": self.load_report(run_id)}

    def list_runs(self) -> list[dict]:
        runs: dict[str, dict] = {}
        if self.out_dir.is_dir():
            for path in self.out_dir.iterdir():
                if not path.is_dir() or not RUN_ID.match(path.name):
                    continue
                if not ((path / "report.json").exists() or (path / "events.jsonl").exists()):
                    continue
                rep = self.load_report(path.name) or {}
                runs[path.name] = {
                    "id": path.name, "project": rep.get("project") or path.name,
                    "source": rep.get("source"), "verdict": rep.get("verdict") or "error",
                    "headline": rep.get("headline") or "No report was written for this run",
                    "started_at": rep.get("started_at"), "metrics": rep.get("metrics") or {},
                    "state": "done",
                }
        for run_id, live in list(self.live.items()):
            if not (live.done or live.saw_done):
                runs[run_id] = live.summary()
        # running first, then newest first (ids start with a timestamp)
        return sorted(runs.values(), key=lambda r: (r["state"] == "running", r["id"]), reverse=True)

    def replay(self, run_id: str) -> Optional[list[dict]]:
        path = self.run_dir(run_id)
        if path is None:
            return None
        text = read_text(path / "events.jsonl", limit=200_000_000)
        if text is None:
            return None
        events = []
        for line in text.splitlines():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return events


class Handler(BaseHTTPRequestHandler):
    server_version = f"FirstRun/{__version__}"
    protocol_version = "HTTP/1.0"  # one response per connection keeps SSE simple

    @property
    def app(self) -> App:
        return self.server.app  # type: ignore[attr-defined]

    # plumbing ------------------------------------------------------------

    def log_request(self, code="-", size="-") -> None:
        if not self.app.quiet:
            path = self.path.split("?", 1)[0]
            code = getattr(code, "value", code)
            sys.stderr.write(f"{self.command} {path} {code}\n")

    def log_message(self, format, *args) -> None:  # noqa: A002
        pass

    def _send(self, status: int, body: bytes, content_type: str, extra: Optional[dict] = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def _json(self, status: int, payload) -> None:
        self._send(status, json.dumps(payload, default=str).encode("utf-8"), "application/json")

    def _error(self, status: int, message: str) -> None:
        self._json(status, {"error": message})

    def _host_ok(self) -> bool:
        if self.app.allow_remote:
            return True
        host = (self.headers.get("Host") or "").strip()
        if not host:
            return True  # HTTP/1.0 clients may omit it, and they cannot be a rebinding page
        if host.startswith("["):
            name = host[: host.index("]") + 1] if "]" in host else host
        else:
            name = host.rsplit(":", 1)[0]
        return _is_loopback(name)

    def _same_origin(self) -> bool:
        origin = self.headers.get("Origin")
        if origin is None:
            return True  # curl and scripts; browsers always send Origin on POST
        if origin == "null":
            return False
        return urlsplit(origin).netloc == (self.headers.get("Host") or "")

    # routing -------------------------------------------------------------

    def do_HEAD(self) -> None:
        self.do_GET()

    def do_GET(self) -> None:
        if not self._host_ok():
            return self._error(HTTPStatus.FORBIDDEN, "unexpected Host header")
        path = urlsplit(self.path).path
        if path.startswith("/api/"):
            return self._api_get(path)
        if path in ("/", "/index.html"):
            return self._static("index.html")
        if path.startswith("/assets/"):
            return self._static(unquote(path[len("/assets/"):]))
        if path == "/favicon.ico":
            if (self.app.web_dir / "favicon.svg").is_file():
                return self._static("favicon.svg")
            return self._send(HTTPStatus.NO_CONTENT, b"", "image/x-icon")
        last = path.rsplit("/", 1)[-1]
        if "." not in last:
            return self._static("index.html")  # client side routes like /runs/<id>
        return self._error(HTTPStatus.NOT_FOUND, "not found")

    def do_POST(self) -> None:
        if not self._host_ok():
            return self._error(HTTPStatus.FORBIDDEN, "unexpected Host header")
        path = urlsplit(self.path).path
        if path != "/api/runs":
            return self._error(HTTPStatus.NOT_FOUND, "not found")
        if not self._same_origin():
            return self._error(HTTPStatus.FORBIDDEN, "cross-origin requests cannot start a run")
        ctype = (self.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
        if ctype != "application/json":
            return self._error(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "send Content-Type: application/json")
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if length <= 0 or length > MAX_BODY:
            return self._error(HTTPStatus.BAD_REQUEST, "request body missing or too large")
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            target, subdir, settings = parse_run_request(body, self.app.out_dir)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return self._error(HTTPStatus.BAD_REQUEST, "body is not valid JSON")
        except BadRequest as exc:
            return self._error(HTTPStatus.BAD_REQUEST, str(exc))
        live = self.app.start(target, subdir, settings)
        if live is None:
            return self._json(HTTPStatus.CONFLICT, {"error": "a check is already running",
                                                    "active_run": self.app.active.id if self.app.active else None})
        self._json(HTTPStatus.ACCEPTED, {"id": live.id, "events_url": f"/api/runs/{live.id}/events",
                                         "report_url": f"/api/runs/{live.id}"})

    def do_PUT(self) -> None:
        self._error(HTTPStatus.METHOD_NOT_ALLOWED, "method not allowed")

    do_DELETE = do_PATCH = do_PUT

    def _api_get(self, path: str) -> None:
        parts = [p for p in path.split("/") if p][1:]  # drop "api"
        if parts == ["status"]:
            return self._json(HTTPStatus.OK, self.app.status())
        if parts == ["runs"]:
            return self._json(HTTPStatus.OK, self.app.list_runs())
        if len(parts) >= 2 and parts[0] == "runs":
            run_id = unquote(parts[1])
            if len(parts) == 2:
                run = self.app.get_run(run_id)
                return self._json(HTTPStatus.OK, run) if run else self._error(HTTPStatus.NOT_FOUND, "unknown run")
            if len(parts) == 3 and parts[2] == "events":
                return self._events(run_id)
            if len(parts) >= 4 and parts[2] == "files":
                return self._file(run_id, unquote("/".join(parts[3:])))
        self._error(HTTPStatus.NOT_FOUND, "unknown endpoint")

    # handlers ------------------------------------------------------------

    def _static(self, rel: str) -> None:
        root = self.app.web_dir.resolve()
        target = (root / rel).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            return self._error(HTTPStatus.NOT_FOUND, "not found")
        if not target.is_file():
            if rel == "index.html":
                return self._send(HTTPStatus.OK, PLACEHOLDER_PAGE.encode(), MIME[".html"])
            return self._error(HTTPStatus.NOT_FOUND, "not found")
        ctype = MIME.get(target.suffix.lower(), "application/octet-stream")
        self._send(HTTPStatus.OK, target.read_bytes(), ctype)

    def _file(self, run_id: str, name: str) -> None:
        path = self.app.run_dir(run_id)
        if path is None:
            return self._error(HTTPStatus.NOT_FOUND, "unknown run")
        log = LOG_NAME.match(name)
        if name in DOWNLOADS:
            target, ctype = path / name, DOWNLOADS[name]
        elif log:
            target, ctype = path / "logs" / log.group(1), "text/plain; charset=utf-8"
        else:
            return self._error(HTTPStatus.NOT_FOUND, "not a downloadable file")
        if not target.is_file():
            return self._error(HTTPStatus.NOT_FOUND, "file not written for this run")
        filename = f"{run_id}-{target.name}"
        self._send(HTTPStatus.OK, target.read_bytes(), ctype,
                   {"Content-Disposition": f'attachment; filename="{filename}"'})

    def _start_sse(self) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(b"retry: 3000\n\n")
        self.wfile.flush()

    def _sse_event(self, event: dict) -> None:
        data = json.dumps(event, default=str)
        self.wfile.write(f"id: {event.get('seq', '')}\ndata: {data}\n\n".encode("utf-8"))
        self.wfile.flush()

    def _events(self, run_id: str) -> None:
        start = 0
        last = self.headers.get("Last-Event-ID")
        query = urlsplit(self.path).query
        since = re.search(r"(?:^|&)since=(\d+)", query)
        if last is not None and last.strip().isdigit():
            start = int(last) + 1
        elif since:
            start = int(since.group(1))

        live = self.app.live.get(run_id)
        replay = None if live is not None else self.app.replay(run_id)
        if live is None and replay is None:
            return self._error(HTTPStatus.NOT_FOUND, "unknown run")
        try:
            self._start_sse()
            if replay is not None:
                for ev in replay:
                    if ev.get("seq", 0) >= start:
                        self._sse_event(ev)
                return
            seq = start
            while True:
                events, done = live.wait_from(seq, timeout=self.app.heartbeat)
                for ev in events:
                    self._sse_event(ev)
                    seq = ev["seq"] + 1
                    if ev["kind"] == "done":
                        return
                if done and not events:
                    return
                if not events:
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return  # the browser went away, nothing to clean up


def make_server(host: str = "127.0.0.1", port: int = 8765, out_dir: Optional[Path] = None, **app_kw) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    server.app = App(Path(out_dir) if out_dir else ROOT / "runs",  # type: ignore[attr-defined]
                     allow_remote=not _is_loopback(host), **app_kw)
    return server


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="python -m firstrun.web", description="FirstRun web UI")
    p.add_argument("--host", default="127.0.0.1", help="interface to listen on (default 127.0.0.1)")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--out", type=Path, default=ROOT / "runs", help="run folders (default runs/ next to FirstRun)")
    p.add_argument("--open", action="store_true", help="open the UI in your browser")
    p.add_argument("--i-know-this-runs-commands", dest="allow_remote", action="store_true",
                   help="allow a non-loopback --host. Anyone who can reach it can make this machine run commands.")
    args = p.parse_args(argv)

    if not _is_loopback(args.host) and not args.allow_remote:
        print(f"refusing to listen on {args.host}: this server runs commands from READMEs on this "
              "machine. Use 127.0.0.1, or pass --i-know-this-runs-commands if you really mean it.",
              file=sys.stderr)
        return 2
    load_own_dotenv()
    try:
        server = make_server(args.host, args.port, args.out)
    except OSError as exc:
        print(f"could not listen on {args.host}:{args.port}: {exc}", file=sys.stderr)
        return 2
    shown = "127.0.0.1" if args.host in ("0.0.0.0", "::") else args.host
    url = f"http://{shown}:{server.server_address[1]}/"
    print(f"FirstRun UI on {url} (Ctrl+C to stop)", flush=True)
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
