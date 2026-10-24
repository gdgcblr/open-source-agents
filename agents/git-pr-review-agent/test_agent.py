"""Automated test suite for git-pr-review-agent."""

import pytest
from models import ReviewSeverity, ReviewCategory, ReviewRequest
from security_scanner import scan_diff_for_security_issues
from git_utils import split_diff_into_files, filter_and_calculate_stats
from agent import GitPRReviewAgent
from main import app
from fastapi.testclient import TestClient

client = TestClient(app)


SAMPLE_CLEAN_DIFF = """diff --git a/calculator.py b/calculator.py
index 1234567..89abcdef 100644
--- a/calculator.py
+++ b/calculator.py
@@ -1,5 +1,7 @@
 def add(a: int, b: int) -> int:
-    return a + b
+    \"\"\"Add two integers safely.\"\"\"
+    return int(a) + int(b)
"""

SAMPLE_LEAK_DIFF = """diff --git a/config.py b/config.py
new file mode 100644
index 0000000..1234567
--- /dev/null
+++ b/config.py
@@ -0,0 +1,5 @@
+# Configuration
+GEMINI_KEY = "AIzaSyB1234567890abcdef1234567890abcdef"
+GH_TOKEN = "ghp_1234567890abcdefghijklmnopqrstuvwxyz"
+def run_code(user_input):
+    return eval(user_input)
"""

SAMPLE_SQL_DIFF = """diff --git a/db.py b/db.py
--- a/db.py
+++ b/db.py
@@ -10,3 +10,4 @@
 def get_user(user_id):
+    cursor.execute(f"SELECT * FROM users WHERE id = '{user_id}'")
"""


def test_security_scanner_clean_diff():
    issues = scan_diff_for_security_issues(SAMPLE_CLEAN_DIFF)
    assert len(issues) == 0


def test_security_scanner_detects_secrets_and_eval():
    issues = scan_diff_for_security_issues(SAMPLE_LEAK_DIFF)
    assert len(issues) >= 3

    severities = [i.severity for i in issues]
    assert ReviewSeverity.CRITICAL in severities

    titles = [i.title for i in issues]
    assert any("Google API" in t for t in titles)
    assert any("GitHub" in t for t in titles)
    assert any("eval()" in t for t in titles)


def test_security_scanner_detects_sql_injection():
    issues = scan_diff_for_security_issues(SAMPLE_SQL_DIFF)
    assert len(issues) >= 1
    assert any("SQL Injection" in i.title for i in issues)


def test_git_utils_filter_lockfiles():
    mock_diff = """diff --git a/package-lock.json b/package-lock.json
--- a/package-lock.json
+++ b/package-lock.json
@@ -1,3 +1,3 @@
-"version": "1.0.0"
+"version": "1.0.1"
diff --git a/src/index.js b/src/index.js
--- a/src/index.js
+++ b/src/index.js
@@ -1,2 +1,3 @@
+// Main entry
 console.log("hello");
"""
    filtered, stats = filter_and_calculate_stats(mock_diff)
    assert "package-lock.json" not in stats["files_changed"]
    assert "src/index.js" in stats["files_changed"]
    assert stats["files_changed_count"] == 1


def test_agent_mock_review_clean():
    agent = GitPRReviewAgent(provider_type="mock")
    report = agent.review_diff_text(SAMPLE_CLEAN_DIFF)

    assert report.verdict in ["APPROVE", "COMMENT"]
    assert report.risk_score < 40
    assert report.pr_summary.title.startswith("feat")
    assert len(report.pr_summary.testing_checklist) > 0


def test_agent_critical_issue_escalates_verdict():
    agent = GitPRReviewAgent(provider_type="mock")
    report = agent.review_diff_text(SAMPLE_LEAK_DIFF)

    assert report.verdict == "REQUEST_CHANGES"
    assert report.risk_score >= 85
    assert len(report.issues) >= 3


def test_markdown_pr_generation():
    agent = GitPRReviewAgent(provider_type="mock")
    report = agent.review_diff_text(SAMPLE_CLEAN_DIFF)
    md = agent.generate_markdown_pr(report)

    assert "# feat" in md
    assert "## Summary" in md
    assert "## Review Overview" in md
    assert "## 📋 Verification Checklist" in md


def test_fastapi_health_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


def test_fastapi_review_endpoint():
    payload = {
        "diff_text": SAMPLE_CLEAN_DIFF,
        "provider": "mock"
    }
    response = client.post("/api/review", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "pr_summary" in data
    assert "risk_score" in data
    assert data["verdict"] in ["APPROVE", "COMMENT"]
