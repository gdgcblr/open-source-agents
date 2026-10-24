import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from murphy.checks import CheckResult, RunContext, build_checks, run_checks
from murphy.config.schema import CheckConfig, PersonaConfig
from murphy.core.verdict import decide


def tool(name, ok=True, fault=None, upstream=True, **args):
    return {"kind": "tool", "tool": name, "args": args, "ok": ok, "fault": fault, "upstream_called": upstream}


def ctx(events, end="goal_met", vars=None, run_dir=Path(".")):
    persona = PersonaConfig(id="p1", goal="g", vars=vars or {})
    return RunContext(run_dir=run_dir, persona=persona, trace=events, end_reason=end, vars=persona.vars)


def check(**cfg):
    return build_checks([CheckConfig.model_validate({"id": "c", **cfg})])[0]


def test_max_calls_per_key_counts_committed_timeouts():
    events = [tool("book", ok=False, fault="timeout_after_commit", order="A12"), tool("book", order="a12")]
    c = check(type="trace", rule="max_calls_per_key", tool="book", key=["order"], max=1, label="dup")
    r = c.run(ctx(events))
    assert not r.passed and r.label == "dup" and "A12" in r.message


def test_max_calls_per_key_ignores_blocked_and_500():
    events = [tool("book", order="A12"), tool("book", ok=False, upstream=False, order="A12"),
              tool("book", ok=False, fault="error_500", upstream=False, order="A12")]
    assert check(type="trace", rule="max_calls_per_key", tool="book", key=["order"]).run(ctx(events)).passed


def test_called_not_called_order():
    events = [tool("check"), tool("book")]
    assert check(type="trace", rule="called", tool="book", min=1, max=1).run(ctx(events)).passed
    assert not check(type="trace", rule="not_called", tool="book").run(ctx(events)).passed
    assert check(type="trace", rule="order", before="check", after="book").run(ctx(events)).passed
    assert not check(type="trace", rule="order", before="book", after="check").run(ctx(events)).passed


def always_true(c):
    return True


def returns_result(c):
    return CheckResult("custom", False, "mine", "nope")


def test_python_check_bool_and_result():
    assert check(type="python", fn="test_checks:always_true").run(ctx([])).passed
    r = check(type="python", fn="test_checks:returns_result").run(ctx([]))
    assert (r.passed, r.label) == (False, "mine")


def test_broken_check_fails_instead_of_crashing():
    def boom(c):
        raise RuntimeError("x")

    from murphy.checks.builtin import PythonCheck
    [r] = run_checks([PythonCheck(id="b", fn=boom, label="err")], ctx([]))
    assert not r.passed and "RuntimeError" in r.message


def test_http_check_with_vars_substitution():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps({"data": {"count": 1 if self.path.endswith("A12") else 0}}).encode()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/pickups?order=${{vars.order}}"
        c = check(type="http", url=url, path="data.count", equals=1)
        assert c.run(ctx([], vars={"order": "A12"})).passed
        assert not c.run(ctx([], vars={"order": "B33"})).passed
    finally:
        server.shutdown()


def test_verdict_labels_and_end_reasons():
    ok = CheckResult("a", True, "dup")
    bad = CheckResult("b", False, "wrong", hint="fix it")
    assert decide([ok], "goal_met") == (True, [], "")
    assert decide([ok, bad], "goal_met") == (False, ["wrong"], "fix it")
    assert decide([ok], "give_up")[1] == ["quit"]
    assert decide([ok], "timeout")[1] == ["stuck"]
    assert decide([ok], "error: boom")[1] == ["error"]
    assert decide([bad], "patience_exhausted")[1] == ["wrong", "quit"]
    assert decide([ok], "give_up", accept_any_end=True)[0] is True


def test_llm_user_parses_json_variants():
    from murphy.users.llm import parse_turn

    assert parse_turn('{"message": "hi", "status": "goal_met"}').status == "goal_met"
    assert parse_turn('```json\n{"message": "hi", "status": "continue"}\n```').message == "hi"
    assert parse_turn('Sure! {"message": "ok", "status": "weird"}').status == "continue"
    assert parse_turn("no json here") is None
