import io
import json
from datetime import date
from unittest.mock import patch

import pytest

from lifeadmin_agent.demo import _next_november_tenth, _ollama_model_info


def test_demo_date_selects_next_november_tenth():
    assert _next_november_tenth(date(2026, 10, 24)) == date(2026, 11, 10)
    assert _next_november_tenth(date(2026, 11, 10)) == date(2026, 11, 10)
    assert _next_november_tenth(date(2026, 11, 11)) == date(2027, 11, 10)


def test_ollama_preflight_reports_exact_installed_model():
    payload = json.dumps({"models": [{"name": "gemma4:e4b"}]}).encode()
    with patch("urllib.request.urlopen", return_value=io.BytesIO(payload)):
        endpoint, model = _ollama_model_info("http://localhost:11434/", "gemma4:e4b")

    assert endpoint == "http://localhost:11434/api/tags"
    assert model == "gemma4:e4b"


def test_ollama_preflight_rejects_uninstalled_model():
    payload = json.dumps({"models": [{"name": "gemma4:e4b"}]}).encode()
    with patch("urllib.request.urlopen", return_value=io.BytesIO(payload)):
        with pytest.raises(RuntimeError, match="ollama pull gemma4:e2b"):
            _ollama_model_info("http://localhost:11434", "gemma4:e2b")
