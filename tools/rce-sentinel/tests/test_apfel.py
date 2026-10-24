"""The real OpenAI-compatible adapter against a local stub that mimics `apfel --serve`."""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import ClassVar

import pytest

from rce_sentinel.config import Settings
from rce_sentinel.memory.casefile import CaseFile
from rce_sentinel.memory.store import Store
from rce_sentinel.models import Finding
from rce_sentinel.orchestrator.budget import Budget
from rce_sentinel.orchestrator.llm import HybridProvider, ModelRegistry
from rce_sentinel.orchestrator.router import Router

LINES = ["import os", "os.system(x)"]
VERDICT = {"verdict": "vulnerable", "confidence": 0.9,
           "evidence": [{"file": "a.py", "line": 2, "quote": "os.system(x)"}],
           "exploit_path": "x reaches os.system", "suggested_fix": "argv list"}


class Stub(BaseHTTPRequestHandler):
    available = True
    loading_left = 1
    requests: ClassVar[list[dict]] = []

    def log_message(self, *args: object) -> None:
        pass

    def _send(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send(200, {"model": "apple-foundationmodel", "context_window": 4096,
                             "model_available": Stub.available})
        elif self.path == "/v1/models":
            self._send(200, {"data": [{"id": "apple-foundationmodel"}]})
        else:
            self._send(404, {})

    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        Stub.requests.append(body)
        if Stub.loading_left > 0:
            Stub.loading_left -= 1
            self._send(503, {"error": {"message": "Model assets are loading."}})
            return
        self._send(200, {"choices": [{"message": {"content": json.dumps(VERDICT)}}],
                         "usage": {"prompt_tokens": 321, "completion_tokens": 45}})


@pytest.fixture
def apfel(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), Stub)
    Stub.available, Stub.loading_left, Stub.requests = True, 1, []
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}/v1"
    monkeypatch.setenv("APFEL_BASE_URL", url)
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:9/v1")  # nothing listens
    yield url
    server.shutdown()


def _router(settings: Settings, mode: str) -> Router:
    registry = ModelRegistry(settings.models, mode)
    return Router(settings, Store(settings.db_path), registry, HybridProvider(registry),
                  Budget(max_tokens=10**6, max_usd=1.0, max_llm_seconds=60), "run",
                  {"rules": "r", "cve_db": "c", "prompt": "p"}, CaseFile(), "rules")


def _finding() -> Finding:
    return Finding(id="f", layer="rule", rule_id="py-os-system", title="t", cwe="CWE-78",
                   file="a.py", line=2, sink="os.system", arg_kind="unknown",
                   context_hash="ctx")


def test_health_probe_controls_availability(settings: Settings, apfel: str) -> None:
    spec = ModelRegistry(settings.models, "auto").all["tier1"][0]
    assert spec.id == "apple-foundationmodel"
    assert ModelRegistry(settings.models, "auto").is_available(spec)
    Stub.available = False  # Apple Intelligence turned off
    assert not ModelRegistry(settings.models, "auto").is_available(spec)


def test_hybrid_uses_real_apfel_and_labelled_mocks(settings: Settings, apfel: str) -> None:
    r = _router(settings, "hybrid")
    out = r.judge(_finding(), LINES)
    assert out.decided_by == "tier1:apple-foundationmodel"  # real, no "(mock)" label
    assert len(Stub.requests) == 2  # one 503 "assets loading", then the retry
    sent = Stub.requests[-1]
    assert sent["model"] == "apple-foundationmodel" and sent["temperature"] == 0
    assert set(sent) <= {"model", "messages", "temperature", "max_tokens", "response_format"}
    rows = r.store.execute("SELECT model, task_type, tokens_in, simulated FROM llm_calls")
    real = [x for x in rows if x["model"] == "apple-foundationmodel"]
    assert real[0]["tokens_in"] == 321 and real[0]["simulated"] == 0
    verifier = next(x for x in rows if x["task_type"] == "verify")
    assert verifier["model"] != "apple-foundationmodel" and verifier["simulated"] == 1


def test_auto_mode_apfel_only(settings: Settings, apfel: str) -> None:
    r = _router(settings, "auto")
    assert [m.id for m in r.registry.available("tier1")] == ["apple-foundationmodel"]
    assert r.registry.available("tier2") == []
    out = r.judge(_finding(), LINES)
    assert out.verdict is not None and out.verdict.verdict == "vulnerable"


def test_prompt_too_big_for_4k_context_skips_apfel(settings: Settings, apfel: str) -> None:
    r = _router(settings, "hybrid")
    assert r.pick("tier1", est_in=500).id == "apple-foundationmodel"
    assert r.pick("tier1", est_in=5000).id != "apple-foundationmodel"


def test_apfel_on_ollama_port_is_not_mistaken_for_ollama(settings: Settings, apfel: str,
                                                          monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_BASE_URL", apfel)  # apfel listening where Ollama would be
    registry = ModelRegistry(settings.models, "auto")
    assert [m.id for m in registry.available("tier1")] == ["apple-foundationmodel"]


def test_schema_constrained_decoding_is_requested(settings: Settings, apfel: str) -> None:
    r = _router(settings, "auto")
    r.judge(_finding(), LINES)
    fmt = Stub.requests[-1]["response_format"]
    assert fmt["type"] == "json_schema" and fmt["json_schema"]["strict"] is True
    schema = fmt["json_schema"]["schema"]
    assert "$ref" not in json.dumps(schema) and "$defs" not in schema
    assert schema["properties"]["confidence"]["maximum"] == 1
    assert schema["additionalProperties"] is False
