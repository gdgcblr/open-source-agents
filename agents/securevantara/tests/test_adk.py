import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from securevantara.adk_agent import (
    get_remediation_guidance,
    read_source_file,
    root_agent,
    run_ast_scan,
    run_full_security_review,
    run_with_adk,
    validate_finding_evidence,
)


class ADKAgentToolsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_run_ast_scan(self):
        (self.root / "sample.py").write_text("eval(user_input)\n")
        res = run_ast_scan(str(self.root))
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["findings_count"], 1)
        self.assertEqual(res["findings"][0]["rule"], "python.dynamic-eval")

    def test_read_source_file(self):
        file = self.root / "test.py"
        file.write_text("a = 1\nb = 2\n")
        res = read_source_file(str(file))
        self.assertEqual(res["status"], "success")
        self.assertIn("1: a = 1", res["content"])
        self.assertIn("2: b = 2", res["content"])

        missing = read_source_file(str(self.root / "nonexistent.py"))
        self.assertEqual(missing["status"], "error")

    def test_validate_finding_evidence(self):
        file = self.root / "code.py"
        file.write_text("x = 10\nreturn eval(data)\ny = 20\n")

        valid = validate_finding_evidence(str(file), 2, "eval(data)")
        self.assertTrue(valid["valid"])
        self.assertEqual(valid["line"], 2)

        invalid_line = validate_finding_evidence(str(file), 10, "eval(data)")
        self.assertFalse(invalid_line["valid"])

        invalid_snippet = validate_finding_evidence(str(file), 1, "eval(data)")
        self.assertFalse(invalid_snippet["valid"])

    def test_get_remediation_guidance(self):
        eval_rem = get_remediation_guidance("dynamic-eval")
        self.assertIn("ast.literal_eval", eval_rem["advice"])

        exec_rem = get_remediation_guidance("exec")
        self.assertIn("dispatch table", exec_rem["safer_alternative"])

        secret_rem = get_remediation_guidance("hardcoded_secret")
        self.assertIn("environment variables", secret_rem["advice"])

    def test_run_full_security_review(self):
        (self.root / "app.py").write_text("eval(x)\n")
        report = run_full_security_review(str(self.root))
        self.assertIn("agent", report)
        self.assertGreaterEqual(len(report["findings"]), 1)

    def test_root_agent_structure_if_adk_installed(self):
        if root_agent is not None:
            self.assertEqual(root_agent.name, "securevantara")
            self.assertEqual(root_agent.model, "gemini-2.5-flash")
            tool_names = [t.__name__ for t in root_agent.tools]
            self.assertIn("run_ast_scan", tool_names)
            self.assertIn("read_source_file", tool_names)
            self.assertIn("validate_finding_evidence", tool_names)
            self.assertIn("get_remediation_guidance", tool_names)

    def test_run_with_adk_mocked(self):
        if root_agent is None:
            with self.assertRaises(RuntimeError):
                run_with_adk("test query")
        else:
            mock_event = MagicMock()
            mock_part = MagicMock()
            mock_part.text = "Audit complete: 1 issue found."
            mock_event.content.parts = [mock_part]

            with patch("google.adk.runners.InMemoryRunner.run_debug", return_value=[mock_event]):
                res = run_with_adk("test query")
                self.assertEqual(res["status"], "success")
                self.assertIn("Audit complete", res["response"])


if __name__ == "__main__":
    unittest.main()
