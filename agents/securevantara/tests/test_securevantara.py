import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from securevantara import adapter
from securevantara.__main__ import main
from securevantara.checks import check, deduplicate


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.binary = self.root / "xalgorix"
        self.binary.write_bytes(b"mock executable")

    def result(self, stdout="xalgorix v4.6.159\n", error=None):
        return dict(stdout=stdout, stderr="", exit_status=0, error=error,
                    truncated=False, timed_out=False)

    def test_missing_executable(self):
        with patch.object(adapter.shutil, "which", return_value=None):
            self.assertIn("not found", adapter.run_xalgorix()["error"])

    def test_command_and_provenance(self):
        with patch.object(adapter.shutil, "which", return_value=str(self.binary)), \
             patch.object(adapter, "execute", side_effect=[self.result(), self.result("not JSON")]) as run:
            result = adapter.run_xalgorix(source=self.root, scope=self.root,
                                         authorized=True, sandboxed=True)
        self.assertEqual(run.call_args.args[0],
                         [str(self.binary), "--source", str(self.root.resolve()), "--code-scan", "review"])
        self.assertEqual(result["findings"], [])
        self.assertEqual(result["runs"][1]["stdout"], "not JSON")
        self.assertEqual(len(result["binary_sha256"]), 64)

    def test_authorization_fails_before_execution(self):
        with patch.object(adapter, "execute") as run:
            for authorized, scope, sandboxed in [(False, self.root, True),
                                                 (True, self.root.parent, True),
                                                 (True, self.root, False),
                                                 (True, None, True)]:
                with self.subTest(authorized=authorized, scope=scope, sandboxed=sandboxed):
                    with self.assertRaises(ValueError):
                        adapter.run_xalgorix(source=self.root, scope=scope,
                                             authorized=authorized, sandboxed=sandboxed)
            run.assert_not_called()

    def test_symlinks_fail_closed(self):
        (self.root / "escape").symlink_to(self.root.parent, target_is_directory=True)
        with self.assertRaises(ValueError):
            adapter.authorize(self.root, self.root, True)

    def test_version_malformed_or_unsupported(self):
        for output in ["{broken", "xalgorix v4.6.160", "xalgorix v4.6.159-malicious"]:
            with patch.object(adapter.shutil, "which", return_value=str(self.binary)), \
                 patch.object(adapter, "execute", return_value=self.result(output)) as run:
                self.assertIn("version", adapter.run_xalgorix()["error"])
                self.assertEqual(run.call_count, 1)

    def test_probe_error_stops_review(self):
        with patch.object(adapter.shutil, "which", return_value=str(self.binary)), \
             patch.object(adapter, "execute", return_value=self.result(error="failed")) as run:
            self.assertEqual(adapter.run_xalgorix()["error"], "failed")
            self.assertEqual(run.call_count, 1)


class FakeProcess:
    """Mock subprocess with OS pipes; no executable or scan is launched."""
    pid = 987654321

    def __init__(self, out=b"", err=b"", status=0, hang=False):
        self.returncode = None if hang else status
        self.stdout = self.pipe(out)
        self.stderr = self.pipe(err)

    @staticmethod
    def pipe(data):
        reader, writer = os.pipe()
        os.write(writer, data)
        os.close(writer)
        return os.fdopen(reader, "rb")

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        if self.returncode is None:
            raise subprocess.TimeoutExpired("mock", timeout)
        return self.returncode


class ExecutionTests(unittest.TestCase):
    def test_shell_disabled_and_env_controls(self):
        process = FakeProcess(b"ok", b"warning")
        with patch.object(adapter.subprocess, "Popen", return_value=process) as popen:
            result = adapter.execute(["/mock", "--version"])
        self.assertFalse(popen.call_args.kwargs["shell"])
        self.assertEqual(popen.call_args.kwargs["stdin"], subprocess.DEVNULL)
        self.assertEqual(popen.call_args.kwargs["env"]["XALGORIX_NO_AUTO_UPDATE"], "1")
        self.assertEqual(popen.call_args.kwargs["env"]["XALGORIX_ALLOW_AUTO_INSTALL"], "false")
        self.assertEqual(result["stdout"], "ok")
        self.assertEqual(result["stderr"], "warning")

    def test_output_truncation_both_streams(self):
        with patch.object(adapter.subprocess, "Popen", return_value=FakeProcess(b"a" * 200, b"b" * 200)):
            result = adapter.execute(["mock"], limit=16)
        self.assertTrue(result["truncated"])
        self.assertEqual(result["stdout"], "a" * 16)
        self.assertEqual(result["stderr"], "b" * 16)

    def test_timeout_kills_process_group(self):
        process = FakeProcess(hang=True)
        def killed(*args):
            process.returncode = -9
        with patch.object(adapter.subprocess, "Popen", return_value=process), \
             patch.object(adapter.os, "killpg", side_effect=killed) as kill:
            result = adapter.execute(["mock"], timeout=0.01)
        self.assertTrue(result["timed_out"])
        self.assertEqual(result["exit_status"], -9)
        kill.assert_called_once()

    def test_nonzero_exit(self):
        with patch.object(adapter.subprocess, "Popen", return_value=FakeProcess(err=b"failure", status=7)):
            result = adapter.execute(["mock"])
        self.assertEqual(result["exit_status"], 7)
        self.assertEqual(result["error"], "non-zero exit status")

    def test_spawn_failure(self):
        with patch.object(adapter.subprocess, "Popen", side_effect=PermissionError("denied")):
            self.assertIn("PermissionError", adapter.execute(["mock"])["error"])

    def test_invalid_resource_limits(self):
        for timeout, limit in [(0, 1), (float("nan"), 1), (float("inf"), 1),
                               (3601, 1), (1, 0), (1, 1048577), (1, True)]:
            with self.subTest(timeout=timeout, limit=limit), self.assertRaises(ValueError):
                adapter.execute(["mock"], timeout, limit)


class ChecksAndReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_evaluation_cases(self):
        # Detection evaluations: explicit positives and negative controls.
        cases = [("eval(user_input)", 1), ("exec(code)", 1),
                 ("# eval(user_input)\nprint('eval(x)')", 0),
                 ("obj.eval(user_input)", 0), ("print('safe')", 0)]
        for source, expected in cases:
            with self.subTest(source=source):
                (self.root / "sample.py").write_text(source)
                findings, errors = check(self.root)
                self.assertEqual(len(findings), expected)
                self.assertEqual(errors, [])
                for finding in findings:
                    self.assertEqual(finding["status"], "needs-review")

    def test_parse_failure_is_not_clean_result(self):
        (self.root / "broken.py").write_text("def (")
        findings, errors = check(self.root)
        self.assertEqual(findings, [])
        self.assertEqual(errors[0]["error"], "SyntaxError")

    def test_dedup_retains_origins_and_locations(self):
        (self.root / "sample.py").write_text("eval(x)\neval(x)")
        findings, _ = check(self.root)
        second = dict(findings[0], provenance=[{"engine": "other"}])
        merged = deduplicate(findings + [second])
        self.assertEqual(len(merged), 2)
        self.assertEqual(len(merged[0]["provenance"]), 2)

    def test_report_generation_and_permissions(self):
        (self.root / "sample.py").write_text("eval(x)")
        report = self.root / "report.json"
        self.assertEqual(main(["check", "--source", str(self.root), "--scope", str(self.root),
                               "--authorized", "--report", str(report)]), 0)
        data = json.loads(report.read_text())
        self.assertEqual(data["schema_version"], "1.0")
        self.assertEqual(len(data["findings"]), 1)
        self.assertEqual(report.stat().st_mode & 0o777, 0o600)
        with self.assertRaises(SystemExit) as caught, patch("sys.stderr", io.StringIO()):
            main(["check", "--report", str(report)])
        self.assertEqual(caught.exception.code, 2)
        self.assertEqual(json.loads(report.read_text()), data)

    def test_authorization_failure_report(self):
        report = self.root / "denied.json"
        self.assertEqual(main(["check", "--source", str(self.root), "--scope", str(self.root),
                               "--report", str(report)]), 2)
        self.assertTrue(json.loads(report.read_text())["errors"])

    def test_missing_source_review_not_probe(self):
        with patch("securevantara.__main__.run_xalgorix") as run:
            self.assertEqual(main(["xalgorix-review", "--report", str(self.root / "missing.json")]), 2)
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
