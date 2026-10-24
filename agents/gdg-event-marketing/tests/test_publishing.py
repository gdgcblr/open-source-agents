import json
import queue
import socket
import threading
import unittest
from http.client import HTTPConnection
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlencode, urlparse

from linkedin_oauth_callback import application
from publishing import (
    LINKEDIN_AUTHORIZATION_URL,
    LINKEDIN_POSTS_URL,
    LINKEDIN_SCOPES,
    LINKEDIN_TOKEN_URL,
    LINKEDIN_USERINFO_URL,
    LinkedInConnection,
    authorize_linkedin,
    build_linkedin_authorization_url,
    get_linkedin_connection,
    publish_linkedin_post,
)
from ui import EventMarketingApp, run_linkedin_connection


class LinkedInPublishingTests(unittest.TestCase):
    def test_authorization_url_requests_minimal_scopes_and_registered_redirect(self):
        redirect_uri = "https://test-service.onrender.com/callback"
        url = build_linkedin_authorization_url("client-id", redirect_uri, "csrf-state")
        query = parse_qs(urlparse(url).query)

        self.assertTrue(url.startswith(LINKEDIN_AUTHORIZATION_URL + "?"))
        self.assertEqual(query["response_type"], ["code"])
        self.assertEqual(query["client_id"], ["client-id"])
        self.assertEqual(query["redirect_uri"], [redirect_uri])
        self.assertEqual(query["state"], ["csrf-state"])
        self.assertEqual(query["scope"], [" ".join(LINKEDIN_SCOPES)])
        self.assertEqual(set(LINKEDIN_SCOPES), {"openid", "profile", "w_member_social"})

    def test_authorization_url_rejects_unregistered_or_non_https_redirects(self):
        for redirect_uri in (
            "http://localhost:8765/callback",
            "https://example.test/other",
            "https://example.test/callback?next=https://attacker.test",
        ):
            with self.subTest(redirect_uri=redirect_uri):
                with self.assertRaisesRegex(ValueError, "registered HTTPS callback"):
                    build_linkedin_authorization_url(
                        "client-id", redirect_uri, "csrf-state"
                    )

    def test_render_callback_forwards_only_to_fixed_localhost(self):
        status_and_headers = {}
        environ = {
            "PATH_INFO": "/callback",
            "REQUEST_METHOD": "GET",
            "QUERY_STRING": urlencode(
                {
                    "code": "auth-code",
                    "state": "csrf-state",
                    "redirect_uri": "https://attacker.test/",
                }
            ),
        }

        def start_response(status, headers):
            status_and_headers["status"] = status
            status_and_headers["headers"] = dict(headers)

        body = application(environ, start_response)
        location = status_and_headers["headers"]["Location"]
        parsed_location = urlparse(location)

        self.assertEqual(status_and_headers["status"], "302 Found")
        self.assertEqual(parsed_location.scheme, "http")
        self.assertEqual(parsed_location.hostname, "127.0.0.1")
        self.assertEqual(parsed_location.port, 8765)
        self.assertEqual(
            parse_qs(parsed_location.query),
            {"code": ["auth-code"], "state": ["csrf-state"]},
        )
        self.assertEqual(status_and_headers["headers"]["Cache-Control"], "no-store")
        self.assertEqual(body, [b""])

    def test_render_callback_rejects_missing_state_and_does_not_redirect(self):
        status_and_headers = {}

        def start_response(status, headers):
            status_and_headers["status"] = status
            status_and_headers["headers"] = dict(headers)

        body = application(
            {
                "PATH_INFO": "/callback",
                "REQUEST_METHOD": "GET",
                "QUERY_STRING": "code=auth-code",
            },
            start_response,
        )

        self.assertEqual(status_and_headers["status"], "400 Bad Request")
        self.assertNotIn("Location", status_and_headers["headers"])
        self.assertIn(b"Invalid LinkedIn callback", body[0])

    @patch("publishing.keyring.set_password")
    @patch("publishing.requests.get")
    @patch("publishing.requests.post")
    @patch("publishing.webbrowser.open")
    def test_oauth_browser_callback_exchanges_code_and_saves_connection(
        self, open_browser, post_request, get_request, save_password
    ):
        with socket.socket() as port_socket:
            port_socket.bind(("127.0.0.1", 0))
            port = port_socket.getsockname()[1]
        redirect_uri = "https://test-service.onrender.com/callback"
        callback_responses = []
        callback_threads = []

        def authorize_in_browser(authorization_url):
            state = parse_qs(urlparse(authorization_url).query)["state"][0]

            def complete_callback():
                callback = HTTPConnection("127.0.0.1", port, timeout=5)
                callback.request(
                    "GET",
                    "/callback?" + urlencode({"code": "auth-code", "state": state}),
                )
                callback_responses.append(callback.getresponse().status)
                callback.close()

            callback_thread = threading.Thread(target=complete_callback, daemon=True)
            callback_threads.append(callback_thread)
            callback_thread.start()
            return True

        open_browser.side_effect = authorize_in_browser
        token_response = Mock()
        token_response.json.return_value = {
            "access_token": "access-token",
            "expires_in": 3600,
        }
        profile_response = Mock()
        profile_response.json.return_value = {
            "sub": "member-123",
            "name": "Test Member",
        }
        post_request.return_value = token_response
        get_request.return_value = profile_response

        connection = authorize_linkedin(
            "client-id",
            "client-secret",
            redirect_uri,
            timeout=5,
            local_callback_port=port,
        )
        for callback_thread in callback_threads:
            callback_thread.join(timeout=5)

        self.assertEqual(connection.person_id, "member-123")
        self.assertEqual(connection.name, "Test Member")
        self.assertEqual(connection.access_token, "access-token")
        self.assertEqual(callback_responses, [200])
        post_request.assert_called_once_with(
            LINKEDIN_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": "auth-code",
                "redirect_uri": redirect_uri,
                "client_id": "client-id",
                "client_secret": "client-secret",
            },
            timeout=30,
        )
        get_request.assert_called_once_with(
            LINKEDIN_USERINFO_URL,
            headers={"Authorization": "Bearer access-token"},
            timeout=30,
        )
        token_response.raise_for_status.assert_called_once_with()
        profile_response.raise_for_status.assert_called_once_with()
        stored_data = json.loads(save_password.call_args.args[2])
        self.assertEqual(stored_data["person_id"], "member-123")
        self.assertEqual(stored_data["access_token"], "access-token")

    def test_ui_worker_redacts_linkedin_client_secret_from_errors(self):
        app = EventMarketingApp.__new__(EventMarketingApp)
        app.results = queue.Queue()

        with patch(
            "ui.authorize_linkedin",
            side_effect=OSError("Request failed using local-client-secret"),
        ):
            app._worker(
                "linkedin_connect",
                run_linkedin_connection,
                ("client-id", "local-client-secret", "https://render.example/callback"),
            )

        action, result_type, message = app.results.get_nowait()
        self.assertEqual((action, result_type), ("linkedin_connect", "error"))
        self.assertIn("[redacted LinkedIn client secret]", message)
        self.assertNotIn("local-client-secret", message)

    def test_ui_blocks_demo_event_from_linkedin_publication(self):
        app = EventMarketingApp.__new__(EventMarketingApp)
        event = {
            "chapter_id": "DEMO-CHAPTER-001 (fictional)",
            "title": "Fictional event",
        }
        app.busy = False
        app.output_widgets = {"linkedin": Mock()}
        app.output_widgets["linkedin"].get.return_value = "Fictional draft"
        app._read_event = Mock(return_value=event)
        app.linkedin_draft_event = dict(event)

        with patch("ui.messagebox.showerror") as showerror:
            app._publish_linkedin()

        showerror.assert_called_once_with(
            "Demo content cannot be published",
            "Switch to a live custom event or a real GDG event before publishing.",
        )

    def test_publish_starts_browser_authorization_when_disconnected(self):
        app = EventMarketingApp.__new__(EventMarketingApp)
        event = {"chapter_id": "", "title": "Community event"}
        app.busy = False
        app.output_widgets = {"linkedin": Mock()}
        app.output_widgets["linkedin"].get.return_value = "Reviewed draft"
        app._read_event = Mock(return_value=event)
        app.linkedin_draft_event = dict(event)
        app.linkedin_account = Mock()
        app._connect_linkedin = Mock()

        with patch("ui.get_linkedin_connection", return_value=None):
            app._publish_linkedin()

        app._connect_linkedin.assert_called_once_with()

    def test_successful_connection_waits_for_explicit_publish_button_click(self):
        app = EventMarketingApp.__new__(EventMarketingApp)
        app.closed = False
        app.results = queue.Queue()
        app.results.put(("linkedin_connect", "success", "Test Member"))
        app._set_busy = Mock()
        app.linkedin_account = Mock()
        app.status = Mock()
        app._publish_linkedin = Mock()
        app.root = Mock()

        app._process_results()

        app.linkedin_account.set.assert_called_once_with("Connected as Test Member")
        app.status.set.assert_called_once_with(
            "LinkedIn connected. Review the draft, then click Publish to LinkedIn."
        )
        app._publish_linkedin.assert_not_called()

    @patch("ui.get_linkedin_connection")
    def test_publish_button_posts_visible_draft_without_an_extra_confirmation(
        self, get_connection
    ):
        app = EventMarketingApp.__new__(EventMarketingApp)
        event = {"chapter_id": "", "title": "Community event"}
        app.busy = False
        app.output_widgets = {"linkedin": Mock()}
        app.output_widgets["linkedin"].get.return_value = "Reviewed draft"
        app._read_event = Mock(return_value=event)
        app.linkedin_draft_event = dict(event)
        app._set_busy = Mock()
        app._start_worker = Mock()
        get_connection.return_value = LinkedInConnection(
            access_token="test-token",
            person_id="member-123",
            name="Test Member",
            expires_at=4_000_000_000,
        )

        app._publish_linkedin()

        app._set_busy.assert_called_once_with(
            True, "Publishing the visible LinkedIn draft…"
        )
        app._start_worker.assert_called_once_with(
            "linkedin_publish", unittest.mock.ANY, "Reviewed draft", "202610"
        )

    @patch("publishing.requests.post")
    @patch("publishing.get_linkedin_connection")
    def test_publish_uses_public_member_posts_api(
        self, get_connection, post_request
    ):
        get_connection.return_value = LinkedInConnection(
            access_token="test-token",
            person_id="member-123",
            name="Test Member",
            expires_at=4_000_000_000,
        )
        response = Mock()
        response.headers = {"x-restli-id": "urn:li:share:123"}
        post_request.return_value = response

        post_id = publish_linkedin_post("  Reviewed event post  ", "202610")

        self.assertEqual(post_id, "urn:li:share:123")
        post_request.assert_called_once_with(
            LINKEDIN_POSTS_URL,
            headers={
                "Authorization": "Bearer test-token",
                "Content-Type": "application/json",
                "LinkedIn-Version": "202610",
                "X-Restli-Protocol-Version": "2.0.0",
            },
            json={
                "author": "urn:li:person:member-123",
                "commentary": "Reviewed event post",
                "visibility": "PUBLIC",
                "distribution": {
                    "feedDistribution": "MAIN_FEED",
                    "targetEntities": [],
                    "thirdPartyDistributionChannels": [],
                },
                "lifecycleState": "PUBLISHED",
                "isReshareDisabledByAuthor": False,
            },
            timeout=30,
        )
        response.raise_for_status.assert_called_once_with()

    @patch("publishing.requests.post")
    @patch("publishing.get_linkedin_connection", return_value=None)
    def test_publish_requires_connection_without_sending_request(
        self, _get_connection, post_request
    ):
        with self.assertRaisesRegex(ValueError, "Connect your LinkedIn account"):
            publish_linkedin_post("Reviewed event post", "202610")

        post_request.assert_not_called()

    @patch("publishing.requests.post")
    def test_publish_rejects_invalid_version_and_empty_draft(self, post_request):
        with self.assertRaisesRegex(ValueError, "draft is empty"):
            publish_linkedin_post("  ", "202610")
        with self.assertRaisesRegex(ValueError, "YYYYMM"):
            publish_linkedin_post("Post", "current")

        post_request.assert_not_called()

    @patch("publishing.keyring.get_password")
    def test_invalid_saved_connection_is_reported(self, get_password):
        get_password.return_value = json.dumps({"access_token": "token"})

        with self.assertRaisesRegex(ValueError, "saved LinkedIn connection is invalid"):
            get_linkedin_connection()


if __name__ == "__main__":
    unittest.main()
