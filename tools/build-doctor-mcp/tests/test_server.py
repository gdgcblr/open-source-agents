import json
import os
import tempfile
import unittest
from pathlib import Path

from build_doctor_mcp.server import analyze_failure, inspect_project, summarize_diagnosis


class BuildDoctorMcpToolsTest(unittest.TestCase):
    def test_analyzes_compilation_failure_with_evidence(self):
        result = json.loads(analyze_failure("error: cannot find symbol\n  symbol: class Widget"))

        self.assertEqual("1.1", result["schema_version"])
        self.assertEqual("compilation", result["failure_type"])
        self.assertTrue(any("cannot find symbol" in item for item in result["evidence"]))
        self.assertTrue(result["hypotheses"])
        self.assertIn("compiler-error", result["scoring"]["matched_signals"])
        self.assertGreaterEqual(result["scoring"]["scores"]["compilation"], 4)
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

    def test_reports_ambiguity_when_signals_tie(self):
        result = json.loads(analyze_failure("module not found; Tests run: 2, Failures: 1"))

        self.assertEqual("low", result["confidence"])
        self.assertIn("Multiple failure categories", " ".join(result["missing_evidence"]))

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

    def test_enforces_workspace_allowlist(self):
        with tempfile.TemporaryDirectory() as allowed, tempfile.TemporaryDirectory() as outside:
            previous = os.environ.get("BUILD_DOCTOR_ALLOWED_ROOT")
            os.environ["BUILD_DOCTOR_ALLOWED_ROOT"] = allowed
            try:
                result = json.loads(inspect_project(outside))
            finally:
                if previous is None:
                    os.environ.pop("BUILD_DOCTOR_ALLOWED_ROOT", None)
                else:
                    os.environ["BUILD_DOCTOR_ALLOWED_ROOT"] = previous

        self.assertIn("outside BUILD_DOCTOR_ALLOWED_ROOT", result["error"])

    def test_redacts_manifest_secrets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "package.json").write_text(
                '{"apiKey":"not-for-output"}\n', encoding="utf-8"
            )

            result = inspect_project(str(root))

        self.assertNotIn("not-for-output", result)
        self.assertIn("[REDACTED]", result)


if __name__ == "__main__":
    unittest.main()
