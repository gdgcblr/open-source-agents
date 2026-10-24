import os
import pytest
from pr_review_agent.guardrails import GuardrailError, remote_preflight, redact, is_sensitive_path
from pr_review_agent.diff_parser import parse_diff
from pr_review_agent.llm import validate_endpoint, LLMError, MockProvider
from pr_review_agent.orchestrator import ReviewOrchestrator

DIFF = 'diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -0,0 +1,1 @@\n+print(1)\n'

def test_remote_default_denied(monkeypatch):
    monkeypatch.delenv('ALLOW_REMOTE_CODE_SHARING', raising=False)
    with pytest.raises(GuardrailError): remote_preflight(parse_diff(DIFF))

def test_remote_secret_blocked(monkeypatch):
    monkeypatch.setenv('ALLOW_REMOTE_CODE_SHARING', 'true')
    with pytest.raises(GuardrailError): remote_preflight(parse_diff(DIFF.replace('print(1)', 'API_KEY = "a-real-looking-token-123456"')))

def test_sensitive_path():
    assert is_sensitive_path('config/.env.production')
    assert is_sensitive_path('private/id_rsa')

def test_redaction():
    assert 'topsecret123456' not in redact('password=topsecret123456')

def test_endpoint_restrictions():
    with pytest.raises(LLMError): validate_endpoint('http://example.com/v1')
    with pytest.raises(LLMError): validate_endpoint('https://evil.example/v1')
    with pytest.raises(LLMError): validate_endpoint('http://192.168.0.1:11434/v1', local=True)
    validate_endpoint('http://127.0.0.1:11434/v1', local=True)

def test_rules_only_never_calls_model():
    class ExplodingProvider(MockProvider):
        def complete(self, *args, **kwargs):
            raise AssertionError('unexpected model call')
    result = ReviewOrchestrator(ExplodingProvider(), use_llm=False).run(DIFF)
    assert result.stats['files_changed'] == 1
