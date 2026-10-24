"""Exercise the public CLI without subprocess dependencies or network calls."""
from contextlib import redirect_stderr, redirect_stdout
import io
import json
import unittest
from unittest.mock import patch

from incident_triage.cli import main


class CliTests(unittest.TestCase):
    def run_cli(self, args):
        output, errors = io.StringIO(), io.StringIO()
        with patch("sys.argv", ["traceguard", *args]), redirect_stdout(output), redirect_stderr(errors):
            code = main()
        return code, output.getvalue(), errors.getvalue()

    def test_security_escalation_without_runtime_flags(self):
        code, text, _ = self.run_cli(["--text", "suspected webshell", "--format", "json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(text)["decision"], "ESCALATE")

    def test_original_sample_command_preserves_operational_diagnosis(self):
        code, text, _ = self.run_cli(["--file", "samples/spring-boot-incident.log", "--format", "json"])
        self.assertEqual(code, 0)
        result = json.loads(text)
        self.assertEqual(result["analysis"]["top_signals"][0]["id"], "database_pool_exhaustion")

    def test_missing_file_actionable_error(self):
        code, _, error = self.run_cli(["--file", "private-filename.log"])
        self.assertEqual(code, 2)
        self.assertNotIn("private-filename", error)
        self.assertIn("does not exist", error)

    def test_invalid_input_has_no_traceback(self):
        code, _, error = self.run_cli(["--text", "unsupported\x00input"])
        self.assertEqual(code, 2)
        self.assertNotIn("Traceback", error)

    def test_high_severity_internal_exposure_still_escalates(self):
        code, text, _ = self.run_cli(["--text", "INFO ready", "--product", "nodejs", "--version", "22.23.3", "--format", "json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(text)["decision"], "ESCALATE")
