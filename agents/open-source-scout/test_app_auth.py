"""Tests for server-side GitHub credential handling."""

import unittest
from unittest.mock import patch

import app as scout_app


class TestGitHubSessionHandling(unittest.TestCase):
    def setUp(self):
        self.client = scout_app.app.test_client()

    def tearDown(self):
        self.client.post("/api/logout")

    @patch("app.verify_github_token", return_value="test-user")
    def test_login_keeps_token_out_of_cookie(self, _verify_token):
        token = "test-token-value"
        response = self.client.post("/api/login", json={"token": token})

        self.assertEqual(response.status_code, 200)
        cookie = response.headers.get("Set-Cookie", "")
        with self.client.session_transaction() as current_session:
            session_id = current_session.get("github_session_id")
            self.assertNotIn("github_token", current_session)

        self.assertNotIn(token, cookie)
        self.assertEqual(scout_app.github_sessions[session_id], (token, "test-user"))

    @patch("app.verify_github_token", return_value="test-user")
    def test_logout_removes_server_side_token(self, _verify_token):
        self.client.post("/api/login", json={"token": "test-token-value"})
        with self.client.session_transaction() as current_session:
            session_id = current_session.get("github_session_id")

        response = self.client.post("/api/logout")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(session_id, scout_app.github_sessions)


if __name__ == "__main__":
    unittest.main()
