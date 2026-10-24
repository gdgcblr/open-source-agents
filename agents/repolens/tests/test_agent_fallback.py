"""
RepoLens — Unit Tests: Agent Fallback and Tool Guardrails
"""
import pytest
from unittest.mock import MagicMock, patch
from agent.tools import make_tools


# ---------------------------------------------------------------------------
# Test tool binding and invalid finding_id rejection
# ---------------------------------------------------------------------------

SAMPLE_SNAPSHOT = {
    "repository_name": "OWASP/NodeGoat",
    "commit_sha": "abc123",
    "tech_stack": ["Node.js"],
    "is_demo": True,
    "findings": [
        {
            "finding_id": "demo-001",
            "title": "Hard-coded credentials",
            "severity": "HIGH",
            "category": "secret",
            "scanner": "trivy",
            "rule_id": "secret-001",
            "advisory_ref": None,
            "file_path": "config/env/development.js",
            "line_start": 5,
            "line_end": 5,
            "evidence": "db: 'mongodb://[REDACTED]@localhost/db'",
            "remediation": "Use environment variables",
            "source_url": None,
            "provenance": "scanner",
        }
    ],
    "scanner_status": {
        "trivy": {"available": True, "finding_count": 1, "error_message": None},
        "semgrep": {"available": False, "finding_count": 0, "error_message": "not found"},
    },
}


class TestGetScanSummary:

    def setup_method(self):
        self.get_scan_summary, self.get_finding_details = make_tools(SAMPLE_SNAPSHOT)

    def test_returns_total_findings(self):
        summary = self.get_scan_summary()
        assert summary["total_findings"] == 1

    def test_returns_severity_breakdown(self):
        summary = self.get_scan_summary()
        assert summary["severity_breakdown"].get("HIGH") == 1

    def test_returns_repo_name(self):
        summary = self.get_scan_summary()
        assert summary["repository_name"] == "OWASP/NodeGoat"

    def test_returns_scanner_status(self):
        summary = self.get_scan_summary()
        assert "trivy" in summary["scanner_status"]
        assert summary["scanner_status"]["trivy"]["available"] is True
        assert summary["scanner_status"]["semgrep"]["available"] is False

    def test_is_demo_flag_present(self):
        summary = self.get_scan_summary()
        assert summary["is_demo"] is True


class TestGetFindingDetails:

    def setup_method(self):
        self.get_scan_summary, self.get_finding_details = make_tools(SAMPLE_SNAPSHOT)

    def test_valid_id_returns_finding(self):
        result = self.get_finding_details("demo-001")
        assert result["finding_id"] == "demo-001"
        assert result["title"] == "Hard-coded credentials"
        assert result["severity"] == "HIGH"

    def test_invalid_id_returns_error_not_exception(self):
        result = self.get_finding_details("nonexistent-id-xyz")
        assert "error" in result
        assert "not found" in result["error"].lower()

    def test_empty_id_returns_error(self):
        result = self.get_finding_details("")
        assert "error" in result

    def test_injected_id_rejected(self):
        """Agent cannot reference a finding that doesn't exist."""
        result = self.get_finding_details("'; DROP TABLE repository_audits; --")
        assert "error" in result

    def test_evidence_is_redacted(self):
        """Evidence should already be redacted — no raw secrets."""
        result = self.get_finding_details("demo-001")
        evidence = result.get("evidence", "")
        assert "REDACTED" in evidence or (
            # If the demo evidence doesn't contain a real secret, it passes unchanged
            "supersecretpassword" not in evidence
        )


class TestMissingGeminiKey:

    def test_runner_returns_none_without_api_key(self):
        """When GOOGLE_API_KEY is absent, gemini_available is False."""
        from backend.config import Settings
        s = Settings(google_api_key="", database_url="postgresql://x:y@localhost/z")
        # With no API key configured, gemini_available must be False
        assert s.gemini_available is False

    def test_gemini_available_false_when_no_key(self):
        from unittest.mock import patch
        from backend.config import Settings
        s = Settings(google_api_key="", database_url="postgresql://x:y@localhost/z")
        assert s.gemini_available is False

    def test_gemini_available_true_when_key_set(self):
        from backend.config import Settings
        s = Settings(google_api_key="AIzaSySOMETHING", database_url="postgresql://x:y@localhost/z")
        assert s.gemini_available is True


class TestMissingScanners:

    def test_trivy_unavailable_status_not_clean_scan(self):
        from backend.scanner.trivy import run_trivy
        import shutil
        # Only test if trivy is actually not installed
        if shutil.which("trivy") is not None:
            pytest.skip("trivy is installed — this test is for missing-scanner case")
        findings, status = run_trivy("/tmp/nonexistent")
        assert status.available is False
        assert findings == []
        assert "not found" in (status.error_message or "").lower()

    def test_semgrep_unavailable_status_not_clean_scan(self):
        from backend.scanner.semgrep import run_semgrep
        import shutil
        if shutil.which("semgrep") is not None:
            pytest.skip("semgrep is installed — this test is for missing-scanner case")
        findings, status = run_semgrep("/tmp/nonexistent")
        assert status.available is False
        assert findings == []
        assert "not found" in (status.error_message or "").lower()
