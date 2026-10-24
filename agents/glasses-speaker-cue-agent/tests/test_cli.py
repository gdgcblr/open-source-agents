import pytest

from glasses_speaker_cue_agent.pipeline import friendly_api_error


@pytest.mark.parametrize(
    ("code", "message", "expected", "kind"),
    [
        ("INVALID_ARGUMENT", "API key not valid. Please pass a valid API key.", "API key", "auth"),
        (429, "RESOURCE_EXHAUSTED", "rate limit", "rate_limited"),
        ("UNAVAILABLE", "503 The model is overloaded", "overloaded", "rate_limited"),
        ("NOT_FOUND", "models/x is not found", "MODEL_NAME", "model"),
        (500, "internal", "--verbose", "error"),
    ],
)
def test_api_errors_become_one_actionable_line(code, message, expected, kind):
    error = friendly_api_error(code, message)
    assert expected in str(error)
    assert "\n" not in str(error)
    assert error.kind == kind
