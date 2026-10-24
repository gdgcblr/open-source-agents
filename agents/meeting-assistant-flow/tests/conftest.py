import json
import pytest
import app as web


@pytest.fixture
def config_file(tmp_path):
    config = {"web": {"client_id": "synthetic-client.apps.googleusercontent.com",
                      "client_secret": "synthetic-test-secret",
                      "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                      "token_uri": "https://oauth2.googleapis.com/token",
                      "redirect_uris": ["http://127.0.0.1:5000/oauth/callback"]}}
    path = tmp_path / "credentials.json"
    path.write_text(json.dumps(config))
    return path


@pytest.fixture
def application(tmp_path, config_file):
    return web.create_app({"TESTING": True, "SECRET_KEY": "test-only-" * 6,
                           "DATABASE": str(tmp_path / "test.sqlite3"),
                           "GOOGLE_CLIENT_CONFIG": str(config_file),
                           "GOOGLE_REDIRECT_URI": "http://127.0.0.1:5000/oauth/callback"})
