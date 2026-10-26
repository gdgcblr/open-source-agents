"""API route, validation, prompt, limiter, and SQLite history tests."""

import json
from types import SimpleNamespace
from uuid import UUID

import pytest

from backend.app import main as api
from backend.app.database import HistoryStore
from backend.app.models import Answer, QueryRequest
from backend.app.rate_limit import RateLimiter
from google.genai import errors

from backend.app.service import ServiceError, _api_error_message, _validate_model_answer, build_prompt


@pytest.fixture
def client(tmp_path):
    """Build route dependencies directly with a fake Gemini answer."""
    state = SimpleNamespace(
        history=HistoryStore(str(tmp_path / "history.db")),
        answer_generator=lambda _request: Answer(
            sql="SELECT email FROM users;",
            explanation="Reads email addresses from users.",
            assumptions=["The table is named users."],
            risks=["The result may contain personal data."],
        ),
    )
    state.history.initialize()
    return SimpleNamespace(app=SimpleNamespace(state=state))


def ask(client, question="List users", dialect="sqlite", schema=None, session_id=None):
    payload = QueryRequest.model_validate({
        "question": question, "dialect": dialect, "schema": schema, "session_id": session_id,
    })
    return api.create_query(payload, client)


def test_query_validates_dialect_and_trims_question(client):
    response = ask(client, "  list users  ", "postgresql")
    assert response.dialect == "postgresql"
    assert response.answer.sql == "SELECT email FROM users;"
    assert response.answer.unverified is True


def test_query_rejects_blank_question_and_unknown_dialect():
    with pytest.raises(ValueError):
        QueryRequest.model_validate({"question": "  "})
    with pytest.raises(ValueError):
        QueryRequest.model_validate({"question": "users", "dialect": "oracle"})


def test_schema_validation_rejects_blank_column():
    with pytest.raises(ValueError):
        QueryRequest.model_validate({
            "question": "list users", "schema": {"tables": [{"name": "users", "columns": [""]}]}
        })


def test_schema_and_dialect_are_in_prompt():
    request = QueryRequest.model_validate({
        "question": "show user email", "dialect": "mysql",
        "schema": {"tables": [{"name": "users", "columns": ["id", "email"]}]},
    })
    prompt = build_prompt(request)
    assert "Selected dialect: mysql" in prompt
    assert '"email"' in prompt
    assert "untrusted data" in prompt


def test_malformed_or_mutating_model_response_is_blocked():
    with pytest.raises(ServiceError) as malformed:
        _validate_model_answer("not JSON")
    assert malformed.value.code == "invalid_model_response"
    for sql in (
        "DROP TABLE users;", "SELECT 1; DROP TABLE users;", "UPDATE users SET active = 0",
        "SELECT email INTO OUTFILE 'users.txt' FROM users",
    ):
        with pytest.raises(ServiceError) as unsafe:
            _validate_model_answer(json.dumps({"sql": sql, "explanation": "Unsafe"}))
        assert unsafe.value.code == "unsafe_model_response"


def test_gemini_api_errors_are_actionable_without_echoing_response_details():
    invalid_key = errors.APIError(403, {"status": "PERMISSION_DENIED", "message": "private key detail"})
    unavailable_model = errors.APIError(404, {"status": "NOT_FOUND", "message": "private model detail"})
    quota = errors.APIError(429, {"status": "RESOURCE_EXHAUSTED", "message": "private quota detail"})

    key_message = _api_error_message(invalid_key)
    assert "API key is valid" in key_message
    assert "private" not in key_message
    assert "GEMINI_MODEL" in _api_error_message(unavailable_model)
    assert "quota" in _api_error_message(quota).lower()


def test_session_can_be_reopened_renamed_and_deleted(client):
    created = ask(client)
    session_id = created.session_id
    assert UUID(str(session_id))
    assert api.list_sessions(client)[0]["id"] == str(session_id)
    reopened = api.get_session(session_id, client)
    assert reopened["messages"][0]["question"] == "List users"
    renamed = api.rename_session(session_id, api.RenameSessionRequest(title="User lookup"), client)
    assert renamed["title"] == "User lookup"
    assert api.delete_session(session_id, client) is None
    assert api.get_session(session_id, client).status_code == 404


def test_query_can_append_to_existing_session(client):
    first = ask(client)
    second = ask(client, "Show their emails", session_id=first.session_id)
    assert second.session_id == first.session_id
    history = api.get_session(first.session_id, client)
    assert len(history["messages"]) == 2


def test_health_does_not_return_configuration(client):
    response = api.health(client)
    assert response.status_code == 200
    assert response.body == b'{"status":"ok","history":"available"}'


def test_history_store_creates_version_and_handles_missing_session(tmp_path):
    store = HistoryStore(str(tmp_path / "direct.db"))
    store.initialize()
    assert store.check()
    with pytest.raises(KeyError):
        store.add_message(UUID("00000000-0000-0000-0000-000000000001"), "Q", {}, "sqlite")


def test_missing_model_configuration_returns_safe_error(client):
    client.app.state.answer_generator = lambda _request: (_ for _ in ()).throw(
        ServiceError(503, "model_not_configured", "Gemini is not configured.")
    )
    with pytest.raises(ServiceError) as error:
        ask(client)
    assert error.value.status_code == 503
    assert error.value.code == "model_not_configured"


def test_rate_limiter_allows_limit_then_resets_after_window():
    limiter = RateLimiter(app=None, max_requests=2, window_seconds=10)
    assert limiter.is_limited("127.0.0.1", now=100) is False
    assert limiter.is_limited("127.0.0.1", now=101) is False
    assert limiter.is_limited("127.0.0.1", now=102) is True
    assert limiter.is_limited("127.0.0.1", now=111) is False
