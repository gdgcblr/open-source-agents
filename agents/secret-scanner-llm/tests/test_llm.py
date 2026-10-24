import json

import httpx
import pytest

from secret_scanner.llm import (MalformedResponse, ModelNotFound, OllamaClient,
                                OllamaUnavailable, normalize_host, parse_triage_json)
from secret_scanner.scanner import scan, scan_text

from . import helpers as H


def one_candidate():
    return scan_text("app.py", f'password = "{H.password()}"\n')[0]


def test_parse_valid_and_fenced_and_trailing_comma():
    assert parse_triage_json(json.dumps(H.verdict("placeholder", 0.8)))["verdict"] == "placeholder"
    fenced = "```json\n" + json.dumps(H.verdict()) + "\n```"
    assert parse_triage_json(fenced)["verdict"] == "real"
    messy = 'Sure! {"verdict": "false positive", "confidence": "85%", "reason": "sha", "remediation": "",}'
    p = parse_triage_json(messy)
    assert p["verdict"] == "false_positive" and p["confidence"] == 0.85


def test_parse_rejects_garbage():
    for bad in ["", "not json", "[]", '{"verdict": "maybe"}', '{"confidence": 1}']:
        with pytest.raises(MalformedResponse):
            parse_triage_json(bad)


def test_request_shape_and_retry_on_malformed():
    cap = []
    t = H.make_ollama_transport(["garbage", "{broken", H.verdict("placeholder", 0.9)], cap)
    cl = OllamaClient(model="gemma3:4b", transport=t)
    res = cl.triage(one_candidate())
    assert res.verdict == "placeholder" and len(cap) == 3
    body = cap[0]
    assert body["options"]["temperature"] == 0 and body["stream"] is False
    assert body["format"]["properties"]["verdict"]["enum"] == ["real", "placeholder", "test_fixture", "false_positive"]
    assert body["model"] == "gemma3:4b" and "/api/chat" not in body  # sanity
    assert "repair" not in json.dumps(cap[0]).lower()
    assert "not valid" in cap[1]["messages"][-1]["content"]


def test_gives_up_after_retries_with_safe_error():
    cl = OllamaClient(transport=H.make_ollama_transport([f"leak {H.password()}"]), max_retries=1)
    with pytest.raises(MalformedResponse) as e:
        cl.triage(one_candidate())
    assert H.password() not in str(e.value)


def test_check_model_missing_and_down():
    cl = OllamaClient(model="gemma3:12b", transport=H.make_ollama_transport([{}], tags=("gemma3:4b",)))
    with pytest.raises(ModelNotFound) as e:
        cl.check()
    assert "ollama pull gemma3:12b" in str(e.value)

    def boom(request):
        raise httpx.ConnectError("refused")

    with pytest.raises(OllamaUnavailable) as e:
        OllamaClient(transport=httpx.MockTransport(boom)).check()
    assert "--no-llm" in str(e.value)


def test_check_accepts_latest_alias():
    OllamaClient(model="gemma3", transport=H.make_ollama_transport([{}], tags=("gemma3:latest",))).check()


def test_normalize_host():
    assert normalize_host("localhost") == "http://localhost:11434"
    assert normalize_host("0.0.0.0:11434") == "http://127.0.0.1:11434"
    assert normalize_host("https://h:1/") == "https://h:1"


def test_end_to_end_scan_with_mock(tmp_path):
    (tmp_path / "a.py").write_text(f'k = "{H.aws()}"\npassword = "changeme-please"\n')
    cl = OllamaClient(transport=H.make_ollama_transport([H.verdict("placeholder", 0.99)]))
    r = scan(tmp_path, client=cl)
    by_rule = {f.candidate.rule: f for f in r.findings}
    assert by_rule["aws_access_key_id"].verdict == "real"  # LLM overruled by safety rule
    assert by_rule["quoted_credential_assignment"].verdict == "placeholder"
    assert len(r.reportable) == 1
