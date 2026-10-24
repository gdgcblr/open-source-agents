import json
import os
import tempfile
import unittest
from pathlib import Path

from build_doctor_mcp.server import analyze_alert, analyze_failure, inspect_project, inspect_test_reports, summarize_diagnosis, verify_resolution


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
        self.assertEqual("observed_failure_only", result["evidence_assessment"]["conclusion"])
        self.assertEqual("unconfirmed", result["evidence_assessment"]["root_cause_status"])

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

    def test_normalizes_latency_alert_without_claiming_a_root_cause(self):
        payload = json.dumps({
            "type": "latency",
            "service_name": "payments-api",
            "environment": "production",
            "metric_name": "p95_latency_ms",
            "current_value": 1200,
            "threshold": 500,
            "unit": "ms",
            "alert_id": "alert-123",
        })

        result = json.loads(analyze_alert("new-relic", payload))

        self.assertEqual("runtime-or-api", result["diagnosis"]["failure_type"])
        self.assertTrue(result["trigger"]["breached"])
        self.assertEqual("unconfirmed", result["diagnosis"]["root_cause_status"])
        self.assertEqual("notify_and_collect_evidence_only", result["action_policy"])

    def test_does_not_treat_an_unbreached_alert_as_a_production_incident(self):
        payload = json.dumps({"event_type": "error_rate", "value": 1, "threshold": 5, "condition": "above"})

        result = json.loads(analyze_alert("cubeapm", payload))

        self.assertFalse(result["trigger"]["breached"])
        self.assertEqual("low", result["diagnosis"]["confidence"])

    def test_alert_adapter_rejects_non_json_provider_payloads(self):
        result = json.loads(analyze_alert("custom-webhook", "not-json"))

        self.assertIn("error", result)

    def test_parses_structured_test_report_evidence(self):
        report = """<testsuite name=\"unit\" tests=\"2\" failures=\"1\" errors=\"0\" skipped=\"0\">
          <testcase classname=\"payments.CheckoutTest\" name=\"rejectsExpiredCard\">
            <failure message=\"expected 200 but was 401\" />
          </testcase>
          <testcase classname=\"payments.CheckoutTest\" name=\"acceptsValidCard\" />
        </testsuite>"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "surefire-reports").mkdir()
            (root / "surefire-reports" / "TEST-checkout.xml").write_text(report, encoding="utf-8")

            result = json.loads(inspect_test_reports(str(root)))

        self.assertEqual("parsed", result["reports"][0]["status"])
        self.assertEqual(2, result["reports"][0]["tests"])
        self.assertEqual("rejectsExpiredCard", result["reports"][0]["failing_tests"][0]["test"].split(".")[-1])
        self.assertIn("401", result["reports"][0]["failing_tests"][0]["message"])

    def test_combined_diagnosis_includes_report_evidence(self):
        report = "<testsuite tests=\"1\" failures=\"1\"><testcase name=\"broken\"><failure message=\"bad\" /></testcase></testsuite>"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "junit.xml").write_text(report, encoding="utf-8")

            result = json.loads(summarize_diagnosis("Tests run: 1, Failures: 1", str(root)))

        self.assertEqual("parsed", result["test_reports"]["reports"][0]["status"])

    def test_reports_ambiguity_when_signals_tie(self):
        result = json.loads(analyze_failure("module not found; Tests run: 2, Failures: 1"))

        self.assertEqual("low", result["confidence"])
        self.assertIn("Multiple failure categories", " ".join(result["missing_evidence"]))

    def test_verifies_only_a_supported_before_after_recovery(self):
        result = json.loads(verify_resolution("error: cannot find symbol", "BUILD SUCCESS"))

        self.assertEqual("verified", result["status"])

    def test_does_not_verify_when_after_output_still_fails(self):
        result = json.loads(verify_resolution("error: cannot find symbol", "error: syntax error"))

        self.assertEqual("inconclusive", result["status"])

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
