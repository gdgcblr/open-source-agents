"""Regression tests against false passes and execution/privacy boundaries."""

import copy
import io
import json
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from first_run_doctor.cli import main
from first_run_doctor.contract import DoctorError, load_contract, read_json
from first_run_doctor.engine import check_project, exit_code
from first_run_doctor.privacy import Redactor
from first_run_doctor.report import compare, markdown, write_reports

GOOD = 'import json\nfrom pathlib import Path\nPath("report.json").write_text(json.dumps({"status":"complete","items":[1]}))\n'
BASE = {
    "schema_version": 1,
    "command": ["{python}", "main.py"],
    "timeout_seconds": 2,
    "inputs": ["main.py"],
    "required_env": [],
    "artifacts": [
        {
            "path": "report.json",
            "format": "json",
            "checks": [
                {"field": "status", "equals": "complete"},
                {"field": "items", "type": "list", "nonempty": True},
            ],
        }
    ],
}


class DoctorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "project"
        self.root.mkdir()
        self.contract = copy.deepcopy(BASE)
        self.source = GOOD
        self.save()

    def save(self):
        (self.root / "main.py").write_text(self.source)
        (self.root / "doctor.json").write_text(json.dumps(self.contract))

    def run_check(self, **kwargs):
        self.save()
        return check_project(self.root, execute=True, environment={}, **kwargs)

    def test_correct_fresh_output_passes_without_changing_source(self):
        report = self.run_check()
        self.assertEqual(report["verification"], "verified")
        self.assertEqual(exit_code(report), 0)
        self.assertFalse((self.root / "report.json").exists())
        self.assertEqual((self.root / "main.py").read_text(), GOOD)

    def test_success_message_cannot_create_a_pass(self):
        self.source = 'print("Success")\n'
        report = self.run_check()
        self.assertEqual(report["execution"]["returncode"], 0)
        self.assertEqual(report["verification"], "failed")
        self.assertEqual(report["diagnosis"]["category"], "output_contract_failure")
        self.assertTrue(any(c["status"] == "skipped" for c in report["checks"]))

    def test_yesterdays_output_cannot_create_a_pass(self):
        previous = '{"status":"complete","items":["old"]}'
        (self.root / "report.json").write_text(previous)
        self.source = 'print("Success")\n'
        self.assertEqual(self.run_check()["verification"], "failed")
        self.assertEqual((self.root / "report.json").read_text(), previous)

    def test_malformed_empty_and_wrong_type_outputs_fail(self):
        for content in (
            "not json",
            '{"status":"complete","items":[]}',
            '{"status":"complete","items":"not a list"}',
            '{"status":"complete","status":"wrong","items":[1]}',
        ):
            with self.subTest(content=content):
                self.source = (
                    f'from pathlib import Path\nPath("report.json").write_text({content!r})\n'
                )
                self.assertEqual(self.run_check()["verification"], "failed")

    def test_boolean_does_not_satisfy_integer_or_numeric_equality(self):
        self.contract["artifacts"][0]["checks"] = [
            {"field": "count", "type": "integer", "equals": 1}
        ]
        self.source = (
            'from pathlib import Path\nPath("report.json").write_text(\'{"count":true}\')\n'
        )
        self.assertEqual(self.run_check()["verification"], "failed")

    def test_nonzero_exit_still_fails_with_valid_artifact(self):
        self.source = GOOD + "raise SystemExit(4)\n"
        self.assertEqual(self.run_check()["verification"], "failed")

    def test_missing_configuration_is_a_preflight_failure_not_runtime_success(self):
        self.contract["required_env"] = ["APP_MODE"]
        report = self.run_check()
        self.assertEqual(report["verification"], "unknown")
        self.assertEqual(report["execution"]["status"], "not_run")
        self.assertEqual(report["diagnosis"]["category"], "missing_configuration")
        self.assertEqual(exit_code(report), 3)

    def test_preview_does_not_execute_or_query_interpreter(self):
        with patch("first_run_doctor.engine.run_process", side_effect=AssertionError("executed")):
            report = check_project(self.root, execute=False, environment={})
        self.assertEqual(report["verification"], "unknown")

    def test_missing_dependency_is_evidence_linked(self):
        self.source = "import first_run_doctor_deliberately_missing_package\n"
        report = self.run_check()
        self.assertEqual(report["verification"], "failed")
        self.assertEqual(report["diagnosis"]["category"], "missing_dependency")
        self.assertIn("EXEC", report["diagnosis"]["evidence_ids"])

    def test_timeout_is_unknown_and_stops_the_process_group(self):
        self.contract["timeout_seconds"] = 0.3
        pid_file = Path(self.temporary.name) / "child-pid"
        self.source = (
            "import subprocess,sys,time\nfrom pathlib import Path\n"
            'p=subprocess.Popen([sys.executable,"-c","import time;time.sleep(30)"])\n'
            f"Path({str(pid_file)!r}).write_text(str(p.pid))\ntime.sleep(30)\n"
        )
        started = time.monotonic()
        report = self.run_check()
        self.assertLess(time.monotonic() - started, 5)
        self.assertEqual(report["verification"], "unknown")
        self.assertEqual(report["execution"]["status"], "timed_out")
        pid = int(pid_file.read_text())
        # A killed child may briefly remain as a zombie. It must not still be running.
        import subprocess

        result = subprocess.run(
            ["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True
        )
        self.assertTrue(not result.stdout.strip() or result.stdout.strip().startswith("Z"))

    def test_large_logs_are_drained_and_capped(self):
        self.source = 'print("x"*200000)\n' + GOOD
        report = self.run_check()
        self.assertEqual(report["verification"], "verified")
        self.assertTrue(report["execution"]["logs_truncated"])
        self.assertLess(len(report["execution"]["stdout"]), 66000)

    def test_oversize_and_fifo_artifacts_are_unknown_without_blocking(self):
        for creation in (
            'Path("report.json").write_bytes(b"x"*2100000)',
            'os.mkfifo("report.json")',
        ):
            self.source = "from pathlib import Path\nimport os\n" + creation + "\n"
            self.assertEqual(self.run_check()["verification"], "unknown")

    def test_output_cannot_traverse_or_overwrite_protected_inputs(self):
        for name in (
            "../outside.json",
            "/tmp/report.json",
            ".",
            "",
            "main.py",
            "doctor.json",
            "input",
        ):
            with self.subTest(name=name):
                self.contract = copy.deepcopy(BASE)
                self.contract["inputs"].append("input/source.txt")
                self.contract["artifacts"][0]["path"] = name
                self.save()
                with self.assertRaises(DoctorError):
                    load_contract(self.root)

    def test_duplicate_and_overlapping_outputs_are_rejected(self):
        self.contract["artifacts"].append(copy.deepcopy(self.contract["artifacts"][0]))
        self.save()
        with self.assertRaises(DoctorError):
            load_contract(self.root)

    def test_contract_rejects_option_entrypoints_and_extreme_timeouts(self):
        self.contract["command"][1] = "-c.py"
        self.save()
        with self.assertRaises(DoctorError):
            load_contract(self.root)
        self.contract = copy.deepcopy(BASE)
        self.contract["timeout_seconds"] = 10**1000
        self.save()
        with self.assertRaises(DoctorError):
            load_contract(self.root)

    def test_config_fifo_and_nonfinite_json_are_rejected(self):
        path = self.root / "not-a-report.json"
        import os

        os.mkfifo(path)
        with self.assertRaises(DoctorError):
            read_json(path)
        path.unlink()
        path.write_text('{"number":1e999}')
        with self.assertRaises(DoctorError):
            read_json(path)

    def test_runtime_artifact_symlink_is_rejected(self):
        self.source = 'from pathlib import Path\nPath("report.json").symlink_to("/etc/passwd")\n'
        self.assertEqual(self.run_check()["verification"], "failed")

    def test_source_symlink_is_rejected_and_env_file_not_copied(self):
        self.source = 'from pathlib import Path\nassert not Path(".env").exists()\n' + GOOD
        (self.root / ".env").write_text("NOT_A_REAL_KEY=local-example\n")
        self.assertEqual(self.run_check()["verification"], "verified")
        (self.root / "escape").symlink_to(Path(self.temporary.name))
        with self.assertRaises(DoctorError):
            self.run_check()

    def test_doctor_model_key_is_not_inherited_and_logs_are_redacted(self):
        self.contract["required_env"] = ["APP_TOKEN"]
        self.source = (
            'import os\nassert "EXPERIENTIAL_API_KEY" not in os.environ\n'
            'print(os.environ["APP_TOKEN"])\n' + GOOD
        )
        self.save()
        fake_secret = "test-only-private-value-for-redaction"
        report = check_project(
            self.root,
            execute=True,
            environment={"APP_TOKEN": fake_secret, "EXPERIENTIAL_API_KEY": "test-only-model-key"},
        )
        self.assertEqual(report["verification"], "verified")
        self.assertNotIn(fake_secret, json.dumps(report))
        self.assertIn("[REDACTED]", report["execution"]["stdout"])

    def test_truncated_secret_line_and_terminal_controls_are_removed(self):
        scrub = Redactor({"APP_TOKEN": "test-only-secret"})
        self.assertNotIn("test-only", scrub.log(b"safe\ntest-only", truncated=True))
        self.assertNotIn("\x1b", scrub.text("\x1b]52;c;clipboard-payload\x07"))

    def test_jev_failure_does_not_change_deterministic_result(self):
        with patch(
            "first_run_doctor.engine.jev_diagnosis",
            return_value={"source": "unavailable", "reason": "offline"},
        ):
            report = self.run_check(diagnose=True)
        self.assertEqual(report["verification"], "verified")
        self.assertEqual(report["jev"]["source"], "unavailable")

    def test_comparison_is_honest_when_expectations_change(self):
        before = self.run_check()
        self.source = 'print("no report")\n'
        after = self.run_check()
        result = compare(before, after)
        self.assertTrue(result["comparable"])
        self.assertNotEqual(before["source"]["sha256"], after["source"]["sha256"])
        after["contract_sha256"] = "changed"
        self.assertFalse(compare(before, after)["comparable"])

    def test_saved_reports_are_redacted_and_not_overwritten(self):
        report = self.run_check()
        destination = Path(self.temporary.name) / "reports"
        write_reports(report, destination)
        self.assertEqual(read_json(destination / "report.json")["verification"], "verified")
        self.assertIn("VERIFIED", (destination / "report.md").read_text())
        with self.assertRaises(DoctorError):
            write_reports(report, destination)

    def test_markdown_escapes_target_controlled_links_and_html(self):
        report = self.run_check()
        report["checks"][0]["detail"] = "[click](https://invalid.example) <script>"
        value = markdown(report)
        self.assertNotIn("[click]", value)
        self.assertNotIn("<script>", value)

    def test_cli_json_output_exit_codes_and_no_execution_default(self):
        for args, expected in (
            (["check", str(self.root), "--format", "json"], 0),
            (["check", str(self.root), "--execute", "--format", "json"], 0),
        ):
            with redirect_stdout(io.StringIO()) as out:
                result = main(args)
            self.assertEqual(result, expected)
            self.assertIn("verification", json.loads(out.getvalue()))
        self.source = 'print("false success")\n'
        self.save()
        with redirect_stdout(io.StringIO()) as out:
            code = main(["check", str(self.root), "--execute", "--format", "json"])
        self.assertEqual(code, 1)

    def test_cli_output_directory_is_validated_before_execution(self):
        with patch("first_run_doctor.cli.check_project", side_effect=AssertionError("executed")):
            with redirect_stderr(io.StringIO()):
                code = main(
                    ["check", str(self.root), "--execute", "--output-dir", str(self.root / "out")]
                )
        self.assertEqual(code, 2)

    def test_packaged_demo_cases(self):
        destination = Path(self.temporary.name) / "demo"
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(["demo", "--output-dir", str(destination)]), 0)
        self.assertTrue(read_json(destination / "summary.json")["comparison"]["comparable"])


if __name__ == "__main__":
    unittest.main()
