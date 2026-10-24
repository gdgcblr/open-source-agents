import json
import tempfile
import unittest
from pathlib import Path

from build_doctor_mcp.server import analyze_failure, inspect_project, summarize_diagnosis


class BuildDoctorMcpToolsTest(unittest.TestCase):
    def test_analyzes_compilation_failure_with_evidence(self):
        result = json.loads(analyze_failure("error: cannot find symbol\n  symbol: class Widget"))

        self.assertEqual("1.0", result["schema_version"])
        self.assertEqual("compilation", result["failure_type"])
        self.assertTrue(any("cannot find symbol" in item for item in result["evidence"]))
        self.assertTrue(result["hypotheses"])
        self.assertTrue(result["remediation_plan"])
        self.assertEqual("pending", result["verification_status"])

    def test_inspects_multiple_language_manifests_without_running_commands(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "package.json").write_text('{"name":"demo"}\n', encoding="utf-8")
            (root / "pyproject.toml").write_text('[project]\nname = "demo"\n', encoding="utf-8")

            result = json.loads(inspect_project(str(root)))

        self.assertEqual(["package.json", "pyproject.toml"], result["manifests"])
        self.assertIn('"name":"demo"', result["content"])
        self.assertIn('name = "demo"', result["content"])

    def test_combines_log_and_project_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "go.mod").write_text("module example.com/demo\n", encoding="utf-8")

            result = json.loads(summarize_diagnosis("Tests run: 3, Failures: 1", str(root)))

        self.assertEqual("test-failure", result["diagnosis"]["failure_type"])
        self.assertIn("go.mod", result["project"]["manifests"])

    def test_rejects_missing_project_path(self):
        result = json.loads(inspect_project("/path/that/does/not/exist"))

        self.assertIn("error", result)

    def test_redacts_credentials_and_marks_truncated_input(self):
        log = "Authorization: Bearer very-secret-token\nGEMINI_API_KEY=super-secret\n" + ("x" * 200001)

        result = json.loads(analyze_failure(log))

        self.assertNotIn("very-secret-token", json.dumps(result))
        self.assertNotIn("super-secret", json.dumps(result))
        self.assertTrue(result["input_truncated"])

    def test_reports_guardrails_in_project_response(self):
        with tempfile.TemporaryDirectory() as directory:
            result = json.loads(inspect_project(directory))

        self.assertIn("guardrails", result)
        self.assertEqual([], result["manifests"])


if __name__ == "__main__":
    unittest.main()
