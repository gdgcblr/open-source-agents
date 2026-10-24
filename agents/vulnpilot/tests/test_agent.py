import pytest
from agent import AIAnalysisError, analyze_findings
from models import Finding

def test_mock_ai_needs_no_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    text = analyze_findings([Finding("r", "msg", "WARNING", "a.py", 1)], mock=True)
    assert "Offline mock analysis" in text

def test_missing_key_is_graceful(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr("agent.load_dotenv", lambda: None)
    with pytest.raises(AIAnalysisError, match="GEMINI_API_KEY"):
        analyze_findings([], mock=False)
