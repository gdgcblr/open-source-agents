import io
import json
import subprocess
import time
from types import SimpleNamespace

import pytest

from migine.adapters import NativeAdapter, serve_connector


@pytest.fixture
def handler_class(tmp_path, monkeypatch):
    captured = {}

    class FakeServer:
        def __init__(self, address, handler):
            captured["handler"] = handler

        def serve_forever(self):
            pass

    monkeypatch.setattr("migine.adapters.HTTPServer", FakeServer)
    token = tmp_path / "test.token"
    serve_connector(token)
    return captured["handler"], token.read_text()


def invoke(handler_class, path, body, authenticated=True, origin=None):
    cls, token = handler_class
    handler = object.__new__(cls)
    encoded = json.dumps(body).encode()
    handler.path = path
    handler.headers = {"Content-Length": str(len(encoded))}
    if authenticated:
        handler.headers["Authorization"] = "Bearer " + token
    if origin:
        handler.headers["Origin"] = origin
    handler.connection = SimpleNamespace(settimeout=lambda _: None)
    handler.rfile = io.BytesIO(encoded)
    handler.wfile = io.BytesIO()
    status = []
    handler.send_error = lambda code, *_args: status.append(code)
    handler.send_response = lambda code: status.append(code)
    handler.send_header = lambda *_args: None
    handler.end_headers = lambda: None
    handler.do_POST()
    return status[-1], handler.wfile.getvalue()


@pytest.mark.parametrize(
    "path,authenticated,origin",
    [
        ("/tool", False, None),
        ("/tool", True, "http://attacker.example"),
        ("/arbitrary", True, None),
    ],
)
def test_connector_rejects_untrusted_requests(
    handler_class, monkeypatch, path, authenticated, origin
):
    def must_not_run(*_args):
        raise AssertionError("Must not call a native tool.")

    monkeypatch.setattr(NativeAdapter, "call", must_not_run)
    assert invoke(handler_class, path, {}, authenticated, origin)[0] == 403


def test_connector_validates_and_forwards_request(handler_class, monkeypatch):
    captured = []

    def fake_call(_self, operation, payload, expires):
        captured.append((operation, payload))
        return []

    monkeypatch.setattr(NativeAdapter, "call", fake_call)
    status, _ = invoke(
        handler_class,
        "/tool",
        {"operation": "calendar.read", "payload": {"days": 7}, "expires": time.time() + 30},
    )
    assert status == 200
    assert captured == [("calendar.read", {"days": 7})]


def test_connector_rejects_expired_request(handler_class):
    assert invoke(handler_class, "/tool", {"expires": time.time() - 1})[0] == 400


def test_connector_rejects_cloud_model(handler_class):
    assert invoke(handler_class, "/ollama/api/chat", {"model": "gemma4:cloud"})[0] == 400


def test_native_write_requires_host_approval(monkeypatch):
    def deny(*_args):
        raise ValueError("User denied")

    def must_not_run(*_args, **_kwargs):
        raise AssertionError("Must not call an app after denial.")

    monkeypatch.setattr("migine.adapters.host_approval", deny)
    monkeypatch.setattr("migine.adapters.subprocess.run", must_not_run)
    monkeypatch.setattr("migine.adapters.sys.platform", "darwin")
    with pytest.raises(ValueError, match="denied"):
        NativeAdapter().call("mail.flag", {"id": "synthetic", "value": True}, time.time() + 30)


def test_mail_keeps_successful_batches_when_one_times_out(monkeypatch):
    def read_batch(command, **kwargs):
        request = json.loads(command[-1])
        assert request["payload"]["limit"] == 1
        if request["payload"]["offset"] == 3:
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])
        return SimpleNamespace(stdout='[{"id":"synthetic"}]')

    monkeypatch.setattr("migine.adapters.sys.platform", "darwin")
    monkeypatch.setattr("migine.adapters.subprocess.run", read_batch)
    result = NativeAdapter().call("mail.read", {"since": "2026-10-01", "limit": 6})
    assert len(result["sources"]) == 5
    assert result["partial"] is True
    assert result["skipped_batches"][0]["offset"] == 3


def test_mail_scan_time_budget_stops_before_more_app_calls(monkeypatch):
    clock = iter([0, 121])
    monkeypatch.setattr("migine.adapters.time", SimpleNamespace(monotonic=lambda: next(clock)))
    monkeypatch.setattr("migine.adapters.sys.platform", "darwin")

    def must_not_run(*_args, **_kwargs):
        raise AssertionError("Scan budget must prevent further app access.")

    monkeypatch.setattr("migine.adapters.subprocess.run", must_not_run)
    result = NativeAdapter().call("mail.read", {"since": "2026-10-01", "limit": 6})
    assert result["sources"] == []
    assert result["scanned_positions"] == 0
    assert result["skipped_batches"][0]["count"] == 6
