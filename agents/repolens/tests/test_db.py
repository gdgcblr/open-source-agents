"""
RepoLens — Unit Tests: Database Layer (mocked)
"""
import json
import pytest
from unittest.mock import MagicMock, patch, call


# ---------------------------------------------------------------------------
# We mock psycopg so tests run without a live PostgreSQL instance.
# ---------------------------------------------------------------------------

class TestDbLayer:

    @patch("backend.db.PSYCOPG_AVAILABLE", True)
    @patch("backend.db._get_connection")
    def test_upsert_audit_returns_id(self, mock_conn_fn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {"id": 42}
        mock_conn.execute.return_value = mock_cursor
        mock_conn_fn.return_value = mock_conn

        from backend.db import upsert_audit
        audit_id = upsert_audit(
            repository_url="https://github.com/OWASP/NodeGoat",
            repository_name="OWASP/NodeGoat",
            commit_sha="abc123",
            scan_status="completed",
            is_demo=True,
            report_json={"findings": []},
            report_markdown="# Report",
            scanner_status={"trivy": {"available": False}},
        )
        assert audit_id == 42

    @patch("backend.db.PSYCOPG_AVAILABLE", True)
    @patch("backend.db._get_connection")
    def test_get_audit_by_id_returns_row(self, mock_conn_fn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {
            "id": 1, "repository_url": "https://github.com/OWASP/NodeGoat"
        }
        mock_conn.execute.return_value = mock_cursor
        mock_conn_fn.return_value = mock_conn

        from backend.db import get_audit_by_id
        row = get_audit_by_id(1)
        assert row is not None
        assert row["id"] == 1

    @patch("backend.db.PSYCOPG_AVAILABLE", True)
    @patch("backend.db._get_connection")
    def test_get_audit_by_id_not_found_returns_none(self, mock_conn_fn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.execute.return_value = mock_cursor
        mock_conn_fn.return_value = mock_conn

        from backend.db import get_audit_by_id
        row = get_audit_by_id(9999)
        assert row is None

    @patch("backend.db.PSYCOPG_AVAILABLE", False)
    def test_raises_when_psycopg_not_installed(self):
        from backend.db import get_db
        with pytest.raises(RuntimeError, match="psycopg3"):
            with get_db():
                pass

    @patch("backend.db.PSYCOPG_AVAILABLE", True)
    @patch("backend.db._get_connection")
    def test_health_check_returns_true_on_success(self, mock_conn_fn):
        mock_conn = MagicMock()
        mock_conn_fn.return_value = mock_conn
        from backend.db import health_check
        assert health_check() is True

    @patch("backend.db.PSYCOPG_AVAILABLE", True)
    @patch("backend.db._get_connection")
    def test_health_check_returns_false_on_failure(self, mock_conn_fn):
        mock_conn_fn.side_effect = Exception("Connection refused")
        from backend.db import health_check
        assert health_check() is False
