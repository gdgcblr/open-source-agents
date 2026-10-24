import unittest

from analyzer import analyze_log


class TestDevOpsPipelineAnalyzer(unittest.TestCase):

    def test_detects_gradle_dependency_failure(self):
        log = "Could not resolve com.example:library:1.0"

        findings = analyze_log(log)

        self.assertTrue(
            any(
                finding["issue"] == "Gradle dependency failure"
                for finding in findings
            )
        )

    def test_detects_authentication_failure(self):
        log = "401 Unauthorized"

        findings = analyze_log(log)

        self.assertTrue(
            any(
                finding["issue"] == "Authentication or permission failure"
                for finding in findings
            )
        )

    def test_detects_sonarqube_quality_gate_failure(self):
        log = "Quality Gate Failed"

        findings = analyze_log(log)

        self.assertTrue(
            any(
                finding["issue"] == "SonarQube quality gate failure"
                for finding in findings
            )
        )

    def test_unknown_log_returns_no_findings(self):
        log = "Pipeline started successfully"

        findings = analyze_log(log)

        self.assertEqual(findings, [])


if __name__ == "__main__":
    unittest.main()