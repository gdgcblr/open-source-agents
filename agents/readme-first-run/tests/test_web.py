import http.client
import json
import threading
import time
from pathlib import Path

import pytest

from firstrun import agent, web
from firstrun.models import Diagnosis, Edit, Evidence, Plan, Report, Round, RunResult, Step, StepResult
from firstrun.report import write_events, write_report

SECRET = "sk-supersecret-value-123"
DIFF = (
    "diff --git a/requirements.txt b/requirements.txt\n--- a/requirements.txt\n+++ b/requirements.txt\n"
    "@@ -1 +1,2 @@\n colorama==0.4.6\n+python-dotenv\n"
)


class FakeCheck:
    """Stands in for agent.run_check: emits a realistic event stream and writes a real run folder."""

    def __init__(self):
        self.gate = threading.Event()
        self.gate.set()
        self.calls = []

    def __call__(self, target, settings, *, subdir=None, on_event=None, run_dir=None):
        self.calls.append({"target": target, "subdir": subdir, "settings": settings, "run_dir": run_dir})
        events = []

        def emit(kind, message, data=None):
            events.append({"seq": len(events), "t": 0.01 * len(events), "kind": kind,
                           "message": message, "data": data})
            on_event(kind, message, data)

        step1 = Step(1, "pip install -r requirements.txt", line=12)
        step2 = Step(2, "python main.py --day 3", kind="run", line=20)
        emit("stage", "understand start", {"stage": "understand", "state": "start"})
        emit("plan", "Plan: 2 steps", {"label": "as documented", "plan": {"steps": []}})
        emit("stage", "understand done", {"stage": "understand", "state": "done"})
        emit("stage", "attempt start", {"stage": "attempt", "state": "start"})
        emit("step_start", "step 1", {"index": 1, "command": step1.command})
        self.gate.wait(10)
        emit("log", "Collecting colorama==0.4.6", None)
        emit("step_end", "step 1", {"index": 1, "status": "passed", "exit_code": 0})
        emit("step_start", "step 2", {"index": 2, "command": step2.command})
        emit("log", "ModuleNotFoundError: No module named 'dotenv'", None)
        emit("step_end", "step 2", {"index": 2, "status": "failed", "exit_code": 1})
        emit("stage", "attempt fail", {"stage": "attempt", "state": "fail"})
        emit("tool_call", "read_file main.py", {"tool": "read_file", "args": {"path": "main.py"}})
        emit("diff", "1 edit", {"round": 1, "diff": DIFF})
        emit("stage", "report start", {"stage": "report", "state": "start"})

        failed = RunResult("as documented", "failed", [
            StepResult(step1, "passed", 0, "ok", 1.0),
            StepResult(step2, "failed", 1, "ModuleNotFoundError: No module named 'dotenv'", 0.1),
        ], 1.1, "local venv", "documented log")
        passed = RunResult("after fix 1", "passed", [
            StepResult(step1, "passed", 0, "ok", 1.0), StepResult(step2, "passed", 0, "quote", 0.1),
        ], 1.1, "local venv", "verify log")
        diag = Diagnosis("missing_dependency", "main.py imports dotenv but requirements.txt does not list it.",
                         evidence=[Evidence("main.py", 3, "imports dotenv")],
                         edits=[Edit("requirements.txt", "", "python-dotenv\n")], confidence="high")
        report = Report(
            project="quote-of-the-day", source=target, started_at="2026-10-24T12:00:00+05:30",
            finished_at="2026-10-24T12:00:05+05:30", verdict="fixed", headline="Fixed it.",
            documented_plan=Plan(steps=[step1, step2], readme_path="README.md"), documented_run=failed,
            rounds=[Round(1, diag, DIFF, None, passed)], final_diff=DIFF, settings=settings.public(),
            metrics={"time_to_first_success": 1.1, "fixes_applied": 1},
        )
        write_report(report, run_dir)
        emit("stage", "report done", {"stage": "report", "state": "done"})
        emit("done", report.headline, {"verdict": "fixed", "run_dir": str(run_dir)})
        write_events(events, run_dir)
        return report, run_dir


@pytest.fixture
def server(tmp_path, monkeypatch):
    fake = FakeCheck()
    monkeypatch.setattr(agent, "run_check", fake)
    monkeypatch.setattr(web.sandbox.DockerSandbox, "available", lambda self: (False, "daemon not running"))
    monkeypatch.setattr(web.llm, "get_llm", lambda *a, **k: None)
    web_dir = tmp_path / "web"
    (web_dir / "js").mkdir(parents=True)
    (web_dir / "index.html").write_text("<!doctype html><title>FirstRun</title>")
    (web_dir / "styles.css").write_text("body{}")
    (web_dir / "js" / "app.js").write_text("export {}")
    (tmp_path / "secret.txt").write_text("do not serve me")
    out = tmp_path / "runs"
    srv = web.make_server("127.0.0.1", 0, out, web_dir=web_dir, quiet=True, heartbeat=0.2)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    srv.fake = fake
    srv.out = out
    srv.port = srv.server_address[1]
    srv.responses = []
    yield srv
    fake.gate.set()
    srv.shutdown()
    srv.server_close()


def request(srv, method, path, body=None, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=10)
    hdrs = {"Host": f"127.0.0.1:{srv.port}"}
    if body is not None and not isinstance(body, (bytes, str)):
        body = json.dumps(body)
        hdrs["Content-Type"] = "application/json"
    hdrs.update(headers or {})
    conn.request(method, path, body=body, headers=hdrs)
    resp = conn.getresponse()
    data = resp.read()
    conn.close()
    srv.responses.append(data)
    return resp, data


def get_json(srv, path):
    resp, data = request(srv, "GET", path)
    return resp.status, json.loads(data)


def sse(srv, path, headers=None):
    """Read an SSE stream to the end and return (events, raw text)."""
    conn = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=10)
    conn.request("GET", path, headers={"Host": f"127.0.0.1:{srv.port}", **(headers or {})})
    resp = conn.getresponse()
    assert resp.status == 200
    assert resp.getheader("Content-Type").startswith("text/event-stream")
    assert resp.getheader("Cache-Control") == "no-cache"
    assert resp.getheader("X-Accel-Buffering") == "no"
    raw = resp.read().decode()
    conn.close()
    srv.responses.append(raw.encode())
    events, ids = [], []
    for block in raw.split("\n\n"):
        for line in block.splitlines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
            elif line.startswith("id: "):
                ids.append(int(line[4:]))
    assert ids == [e["seq"] for e in events]
    return events, raw


def start_run(srv, **extra):
    body = {"target": "examples/quote-of-the-day", "sandbox": "local", "offline": True, **extra}
    resp, data = request(srv, "POST", "/api/runs", body)
    assert resp.status == 202, data
    return json.loads(data)


def wait_done(srv, run_id):
    for _ in range(100):
        status, run = get_json(srv, f"/api/runs/{run_id}")
        if run["state"] == "done":
            return run
        time.sleep(0.05)
    raise AssertionError("run never finished")


def test_status(server):
    status, data = get_json(server, "/api/status")
    assert status == 200
    assert data["docker"] == {"ok": False, "detail": "daemon not running"}
    assert data["gemini"] == {"ok": False, "model": None, "label": "Gemini"}
    assert data["defaults"]["sandbox"] == "docker" and data["busy"] is False
    names = {e["name"]: e for e in data["examples"]}
    assert {"quote-of-the-day", "standup-notes", "gemini-haiku"} <= set(names)
    q = names["quote-of-the-day"]
    assert q["path"] == "examples/quote-of-the-day" and q["summary"].endswith(".")
    assert q["expected_verdict"] == "fixed"
    assert names["gemini-haiku"]["expected_verdict"] == "blocked"


@pytest.mark.parametrize("body,status", [
    ({}, 400),
    ({"target": "  "}, 400),
    ({"target": "x", "sandbox": "vm"}, 400),
    ({"target": "x", "max_rounds": 9}, 400),
    ({"target": "x", "max_rounds": "two"}, 400),
    ({"target": "x", "offline": "maybe"}, 400),
    ({"target": "x", "image": "python:3.12; rm -rf /"}, 400),
    ({"target": "x", "secrets": f"not a pair {SECRET}\nbad key!={SECRET}"}, 400),
])
def test_post_validation(server, body, status):
    resp, data = request(server, "POST", "/api/runs", body)
    assert resp.status == status
    assert "error" in json.loads(data)
    assert SECRET.encode() not in data
    assert server.fake.calls == []


def test_post_needs_json_and_same_origin(server):
    resp, _ = request(server, "POST", "/api/runs", b'{"target": "x"}', {"Content-Type": "text/plain"})
    assert resp.status == 415
    resp, _ = request(server, "POST", "/api/runs", b"{not json", {"Content-Type": "application/json"})
    assert resp.status == 400
    resp, _ = request(server, "POST", "/api/runs", {"target": "x"}, {"Origin": "https://evil.example"})
    assert resp.status == 403
    resp, _ = request(server, "GET", "/api/status", headers={"Host": "evil.example:8765"})
    assert resp.status == 403  # DNS rebinding
    assert server.fake.calls == []


def test_settings_mapping_and_example_paths(server):
    run = start_run(server, max_rounds=0, watch_seconds=7, image="python:3.11", secrets="A_KEY=1\n# c\nexport B=two")
    wait_done(server, run["id"])
    call = server.fake.calls[0]
    s = call["settings"]
    assert s.sandbox == "local" and s.offline is True and s.repair is False and s.max_rounds == 1
    assert s.watch_seconds == 7 and s.image == "python:3.11"
    assert s.env == {"A_KEY": "1", "B": "two"}
    assert s.out_dir == server.out
    # example paths are resolved against the FirstRun folder, not the cwd
    assert Path(call["target"]) == (web.ROOT / "examples" / "quote-of-the-day").resolve()
    assert call["run_dir"] == server.out / run["id"]
    assert run["events_url"] == f"/api/runs/{run['id']}/events"


def test_live_stream_conflict_and_listing(server):
    server.fake.gate.clear()
    run = start_run(server)
    resp, data = request(server, "POST", "/api/runs", {"target": "examples/standup-notes"})
    assert resp.status == 409 and json.loads(data)["active_run"] == run["id"]

    status, runs = get_json(server, "/api/runs")
    assert runs[0]["id"] == run["id"] and runs[0]["state"] == "running"
    status, one = get_json(server, f"/api/runs/{run['id']}")
    assert one == {"id": run["id"], "state": "running", "report": None}
    assert get_json(server, "/api/status")[1]["busy"] is True

    result = {}
    reader = threading.Thread(target=lambda: result.update(zip(("events", "raw"), sse(server, run["events_url"]))))
    reader.start()
    time.sleep(0.5)  # longer than the heartbeat, so a ping has to go out
    server.fake.gate.set()
    reader.join(10)
    events = result["events"]
    assert [e["seq"] for e in events] == list(range(len(events)))
    assert events[-1]["kind"] == "done" and events[-1]["data"]["verdict"] == "fixed"
    stages = [e["data"]["stage"] for e in events if e["kind"] == "stage" and e["data"]["state"] == "start"]
    assert stages == ["understand", "attempt", "report"]
    assert ": ping" in result["raw"]

    done = wait_done(server, run["id"])
    assert done["report"]["verdict"] == "fixed"
    assert done["report"]["metrics"]["time_to_first_success"] == 1.1
    status, runs = get_json(server, "/api/runs")
    assert runs[0]["verdict"] == "fixed" and runs[0]["state"] == "done"


def test_replay_and_resume_from_disk(server, tmp_path):
    run = start_run(server)
    wait_done(server, run["id"])
    live_events, _ = sse(server, run["events_url"])

    # a fresh server (say after a restart) only has the folder on disk
    server.app.live.clear()
    replayed, _ = sse(server, run["events_url"])
    assert [e["kind"] for e in replayed] == [e["kind"] for e in live_events]
    assert replayed[-1]["kind"] == "done"

    resumed, _ = sse(server, run["events_url"], {"Last-Event-ID": "3"})
    assert resumed[0]["seq"] == 4 and resumed[-1]["kind"] == "done"
    since, _ = sse(server, run["events_url"] + "?since=10")
    assert since[0]["seq"] == 10

    # runs made by the CLI land in the same folder and show up too
    cli_dir = server.out / "20200101-000000-old-project"
    cli_dir.mkdir()
    (cli_dir / "report.json").write_text(json.dumps({"project": "old-project", "verdict": "passed", "headline": "ok"}))
    ids = [r["id"] for r in get_json(server, "/api/runs")[1]]
    assert ids[-1] == "20200101-000000-old-project" and run["id"] in ids


def test_file_downloads(server):
    run = start_run(server)
    wait_done(server, run["id"])
    base = f"/api/runs/{run['id']}/files/"
    resp, data = request(server, "GET", base + "fix.patch")
    assert resp.status == 200 and data.decode() == DIFF
    assert resp.getheader("Content-Disposition") == f'attachment; filename="{run["id"]}-fix.patch"'
    for name in ("report.md", "report.json", "comment.md", "verified-setup.sh", "events.jsonl", "logs/as-documented.log"):
        resp, _ = request(server, "GET", base + name)
        assert resp.status == 200, name
    (server.out / run["id"] / "notes.txt").write_text("private")
    for bad in ("notes.txt", "../../secret.txt", "logs/../report.json", "%2e%2e/%2e%2e/secret.txt", "logs/x.txt"):
        resp, data = request(server, "GET", base + bad)
        assert resp.status == 404, bad
        assert b"private" not in data and b"do not serve" not in data
    for bad_run in ("..", "%2e%2e", "nope"):
        resp, _ = request(server, "GET", f"/api/runs/{bad_run}/files/report.md")
        assert resp.status == 404


def test_static_and_unknown_routes(server):
    resp, data = request(server, "GET", "/")
    assert resp.status == 200 and resp.getheader("Content-Type").startswith("text/html") and b"FirstRun" in data
    resp, _ = request(server, "GET", "/assets/styles.css")
    assert resp.getheader("Content-Type").startswith("text/css")
    resp, _ = request(server, "GET", "/assets/js/app.js")
    assert resp.getheader("Content-Type").startswith("text/javascript")
    for bad in ("/assets/../secret.txt", "/assets/%2e%2e/secret.txt", "/assets/missing.css"):
        resp, data = request(server, "GET", bad)
        assert resp.status == 404 and b"do not serve" not in data
    resp, data = request(server, "GET", "/runs/some-id")  # client side route
    assert resp.status == 200 and b"FirstRun" in data
    resp, data = request(server, "GET", "/api/nope")
    assert resp.status == 404 and json.loads(data)["error"]
    resp, _ = request(server, "GET", "/api/runs/nope")
    assert resp.status == 404
    resp, _ = request(server, "GET", "/api/runs/nope/events")
    assert resp.status == 404


def test_secrets_never_leave_the_settings(server):
    run = start_run(server, secrets=f"GEMINI_API_KEY={SECRET}")
    wait_done(server, run["id"])
    assert server.fake.calls[0]["settings"].env == {"GEMINI_API_KEY": SECRET}
    sse(server, run["events_url"])
    get_json(server, f"/api/runs/{run['id']}")
    get_json(server, "/api/runs")
    for name in ("report.md", "report.json", "comment.md", "events.jsonl"):
        request(server, "GET", f"/api/runs/{run['id']}/files/{name}")
    assert all(SECRET.encode() not in body for body in server.responses)
    for f in server.out.rglob("*"):
        if f.is_file():
            assert SECRET not in f.read_text()
    report = json.loads((server.out / run["id"] / "report.json").read_text())
    assert report["settings"]["env_keys"] == ["GEMINI_API_KEY"]


def test_crashing_run_still_finishes(server, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(agent, "run_check", boom)
    run = start_run(server)
    events, _ = sse(server, run["events_url"])
    assert events[-1]["kind"] == "done" and events[-1]["data"]["verdict"] == "error"
    assert any("kaboom" in e["message"] for e in events)
    for _ in range(50):
        if not get_json(server, "/api/status")[1]["busy"]:
            break
        time.sleep(0.05)
    assert get_json(server, "/api/status")[1]["busy"] is False
    assert (server.out / run["id"] / "events.jsonl").exists()


def test_refuses_public_host_without_flag(capsys):
    assert web.main(["--host", "0.0.0.0", "--port", "0"]) == 2
    assert "refusing to listen" in capsys.readouterr().err


def test_missing_local_folder_is_a_form_error(server):
    resp, data = request(server, "POST", "/api/runs", {"target": "does/not/exist", "sandbox": "local"})
    assert resp.status == 400
    assert "no folder at does/not/exist" in json.loads(data)["error"]
    assert server.fake.calls == []


def test_parse_request_unit():
    target, subdir, s = web.parse_run_request(
        {"target": "https://github.com/a/b", "subdir": "/agents/x/", "max_rounds": "3", "offline": "true"},
        Path("runs"),
    )
    assert target == "https://github.com/a/b" and subdir == "agents/x"
    assert s.max_rounds == 3 and s.repair is True and s.offline is True
