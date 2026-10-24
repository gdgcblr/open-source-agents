"""Unit tests for scripts/seed_demo.py."""
from unittest.mock import MagicMock, patch
import pytest

from scripts.seed_demo import (
    DEMO_REPORT,
    DEMO_SCANNER_STATUS,
    DEMO_URL,
    DEMO_REPO_NAME,
    build_demo_markdown,
    seed,
)


def test_demo_report_structure():
    """Verify demo report structure and flags."""
    assert DEMO_REPORT["is_demo"] is True
    assert DEMO_REPORT["repository_url"] == DEMO_URL
    assert DEMO_REPORT["repository_name"] == DEMO_REPO_NAME
    assert len(DEMO_REPORT["findings"]) == 5
    assert DEMO_REPORT["ai_available"] is False

    for finding in DEMO_REPORT["findings"]:
        assert "finding_id" in finding
        assert "title" in finding
        assert "severity" in finding
        assert finding["severity"] in {"CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"}
        assert "file_path" in finding
        assert "remediation" in finding


def test_build_demo_markdown():
    """Verify demo markdown formatting."""
    md = build_demo_markdown(DEMO_REPORT)
    assert "# RepoLens Security Audit: OWASP/NodeGoat" in md
    assert "ILLUSTRATIVE DEMO REPORT" in md
    assert "### [HIGH] Hard-coded MongoDB connection string" in md
    assert "config/env/development.js:5" in md
    assert "## Findings Summary" in md


def test_seed_mocked_db():
    """Verify seed() calls upsert_audit with expected arguments."""
    with patch("backend.db.get_audit_by_url", return_value={"id": 1, "is_demo": True}), \
         patch("backend.db.upsert_audit", return_value=1) as mock_upsert:
        seed()
        assert mock_upsert.called
        kwargs = mock_upsert.call_args.kwargs
        assert kwargs["repository_url"] == DEMO_URL
        assert kwargs["is_demo"] is True
        assert kwargs["scan_status"] == "completed"
        assert kwargs["report_json"] == DEMO_REPORT
