import io
import json
import os
import tempfile
import unittest

from cli import DEMO_SCRIPT, analyze, demo, run_protected

FAKE_GITHUB = "ghp_" + "A1" * 18  # synthetic


def run_analyze(lines):
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    try:
        out = io.StringIO()
        return analyze(f.name, out), out.getvalue()
    finally:
        os.unlink(f.name)


def call(tool, **kw):
    return json.dumps({"tool": tool, **kw})


class DemoTests(unittest.TestCase):
    def test_demo_shows_blocks_and_halts(self):
        out = io.StringIO()
        self.assertEqual(demo(out), 0)
        text = out.getvalue()
        self.assertIn("BLOCKED [guardrail] env_file_access", text)
        self.assertIn("BLOCKED [cycle]", text)
        self.assertIn("agent halted", text)
        self.assertIn("17 calls executed, 8 failed", text)


class AnalyzeTests(unittest.TestCase):
    def test_clean_trace_exits_zero(self):
        code, out = run_analyze([call("a", args={"x": 1}, ok=True), call("b")])
        self.assertEqual(code, 0)
        self.assertIn("2 calls in 1 session(s)", out)

    def test_malformed_lines_reported_without_stopping(self):
        code, out = run_analyze(["{not json", "[1,2]", call(""), json.dumps({"tool": "t", "args": []}),
                                 json.dumps({"tool": "t", "ok": "yes"}), "", call("good")])
        self.assertEqual(code, 1)
        self.assertIn("line 1: MALFORMED invalid JSON", out)
        self.assertIn("line 2: MALFORMED expected a JSON object", out)
        self.assertIn("line 3: MALFORMED missing or empty 'tool'", out)
        self.assertIn("line 4: MALFORMED 'args' must be an object", out)
        self.assertIn("line 5: MALFORMED 'ok' must be true or false", out)
        self.assertIn("line 7: [default] good", out)
        self.assertIn("5 malformed lines", out)

    def test_malformed_line_with_secret_not_echoed(self):
        _, out = run_analyze(['{"tool": "x", "args": "' + FAKE_GITHUB])
        self.assertNotIn(FAKE_GITHUB, out)

    def test_repeat_and_cycle_detected(self):
        _, out = run_analyze([call("s")] * 3 + [call("a"), call("b"), call("a"), call("b")])
        self.assertIn("line 3: [default] s {} -> WOULD BLOCK [repeat]", out)
        self.assertIn("line 7: [default] b {} -> WOULD BLOCK [cycle]", out)

    def test_errors_from_ok_field(self):
        _, out = run_analyze([call(f"t{i}", ok=False) for i in range(4)])
        self.assertIn("line 4: [default] t3 {} -> WOULD BLOCK [errors]", out)

    def test_sessions_isolated(self):
        _, out = run_analyze([call("s", session="a"), call("s", session="a"),
                              call("s", session="b"), call("s", session="a")])
        self.assertIn("line 3: [b] s {} -> allowed", out)
        self.assertIn("line 4: [a] s {} -> WOULD BLOCK [repeat]", out)
        self.assertIn("in 2 session(s)", out)

    def test_secrets_redacted_and_guardrails_flagged(self):
        code, out = run_analyze([call("http", args={"auth": FAKE_GITHUB}),
                                 call("shell", args={"cmd": "rm -rf /"})])
        self.assertEqual(code, 1)
        self.assertNotIn(FAKE_GITHUB, out)
        self.assertIn("[REDACTED:github_token]", out)
        self.assertIn("SECRETS github_token", out)
        self.assertIn("GUARDRAIL destructive_command", out)

    def test_missing_file_exits_two(self):
        out = io.StringIO()
        self.assertEqual(analyze("does-not-exist.jsonl", out), 2)


class ProtectedExecutionTests(unittest.TestCase):
    def run_script(self, script):
        executed = []
        count = run_protected(script, lambda t, a, ok: executed.append((t, a)) or ok, io.StringIO())
        return count, executed

    def test_guardrail_blocked_call_never_executed(self):
        count, executed = self.run_script(DEMO_SCRIPT)
        self.assertNotIn(("read_file", {"path": "config/.env"}), executed)
        self.assertEqual(count, len(executed))

    def test_breaker_blocked_call_never_executed_and_run_halts(self):
        count, executed = self.run_script(DEMO_SCRIPT)
        self.assertEqual([t for t, _ in executed], ["search", "fetch", "search"])
        self.assertEqual(count, 3)

    def test_execute_result_drives_error_counter(self):
        script = [(f"t{i}", {}, False) for i in range(5)]
        count, executed = self.run_script(script)
        self.assertEqual(count, 3)  # fourth call blocked after 3 consecutive failures


class AnalyzeEdgeTests(unittest.TestCase):
    def test_failed_call_not_reported_as_ok(self):
        _, out = run_analyze([call("fetch", ok=False), call("search", ok=True), call("other")])
        self.assertIn("line 1: [default] fetch {} -> allowed (call FAILED)", out)
        self.assertIn("line 2: [default] search {} -> allowed (call succeeded)", out)
        self.assertIn("line 3: [default] other {} -> allowed\n", out)
        self.assertNotIn("-> ok", out)

    def test_failed_call_shown_alongside_block(self):
        _, out = run_analyze([call("s", ok=False)] * 3)
        self.assertIn("line 3: [default] s {} -> WOULD BLOCK [repeat]", out)
        self.assertIn("(call FAILED)", out.splitlines()[2])

    def test_malformed_lines_with_secrets_never_echoed(self):
        lines = [
            '{"tool": "x", "args": {"k": "' + FAKE_GITHUB,  # truncated JSON
            '["' + FAKE_GITHUB + '"]',  # not an object
            json.dumps({"tool": FAKE_GITHUB, "args": FAKE_GITHUB}),  # bad args type
            json.dumps({"tool": "t", "ok": FAKE_GITHUB}),  # bad ok type
            json.dumps({"tool": "t", "session": {"s": FAKE_GITHUB}}),  # bad session type
            FAKE_GITHUB,  # not JSON at all
        ]
        code, out = run_analyze(lines)
        self.assertEqual(code, 1)
        self.assertNotIn(FAKE_GITHUB, out)
        self.assertNotIn("A1A1", out)
        self.assertIn("6 malformed lines", out)

    def test_truncated_line_reports_its_own_column(self):
        _, out = run_analyze(['{"tool": "a"'])
        self.assertIn("at column 13)", out)

    def test_secret_in_tool_and_session_names_redacted(self):
        _, out = run_analyze([call(FAKE_GITHUB, session=FAKE_GITHUB)])
        self.assertNotIn(FAKE_GITHUB, out)

    def test_incomplete_records(self):
        code, out = run_analyze([json.dumps({}), json.dumps({"args": {}}), json.dumps({"tool": None}),
                                 json.dumps({"tool": 5}), "null", "42"])
        self.assertEqual(out.count("MALFORMED"), 6)
        self.assertIn("0 calls in 0 session(s)", out)

    def test_whitespace_only_and_trailing_lines_ignored(self):
        code, out = run_analyze(["   ", call("a"), "\t", ""])
        self.assertEqual(code, 0)
        self.assertIn("1 calls in 1 session(s)", out)

    def test_many_sessions_isolated_for_errors(self):
        lines = [call("t", session="bad", ok=False, args={"i": i}) for i in range(3)]
        lines += [call("t", session="good", args={"i": 0}), call("t", session="bad", args={"i": 9})]
        _, out = run_analyze(lines)
        self.assertIn("line 4: [good] t", out)
        self.assertNotIn("WOULD BLOCK", out.splitlines()[3])
        self.assertIn("WOULD BLOCK [errors]", out.splitlines()[4])

    def test_non_utf8_file_exits_two(self):
        with tempfile.NamedTemporaryFile("wb", suffix=".jsonl", delete=False) as f:
            f.write(b"\xff\xfe\x00bad")
        try:
            self.assertEqual(analyze(f.name, io.StringIO()), 2)
        finally:
            os.unlink(f.name)


if __name__ == "__main__":
    unittest.main()
