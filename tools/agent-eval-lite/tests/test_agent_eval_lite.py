import io
import json
import sys
import urllib.error
from pathlib import Path

import pytest

# Ensure module is found when running pytest from any directory or CLI entrypoint
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import agent_eval_lite as ev


def test_normalize_host():
    assert ev.normalize_host("localhost:11434") == "http://localhost:11434"
    assert ev.normalize_host("http://localhost:11434/") == "http://localhost:11434"
    assert ev.normalize_host("https://ollama.example.com:443/api") == "https://ollama.example.com:443"


def test_normalize_host_rejects_empty():
    with pytest.raises(ValueError, match="cannot be empty"):
        ev.normalize_host(" ")


def test_normalize_host_rejects_missing_hostname():
    for malformed in ("http://", "https://", "http://:8000"):
        with pytest.raises(ValueError, match="missing hostname"):
            ev.normalize_host(malformed)


def test_normalize_host_rejects_invalid_port():
    with pytest.raises(ValueError, match="Port must be between 1 and 65535|Invalid port"):
        ev.normalize_host("http://localhost:70000")
    with pytest.raises(ValueError, match="Invalid port"):
        ev.normalize_host("http://localhost:notaport")


def test_normalize_host_rejects_unsupported_scheme():
    with pytest.raises(ValueError, match="Host must use http:// or https://"):
        ev.normalize_host("ftp://localhost:11434")


def test_dataset_loads_example():
    example_path = Path(__file__).resolve().parent.parent / "examples" / "cases.json"
    cases = ev.load_dataset(example_path)
    assert len(cases) == 3
    assert cases[0]["id"] == "capital-france"


def test_dataset_rejects_duplicate_ids(tmp_path):
    path = tmp_path / "cases.json"
    path.write_text(json.dumps([
        {"id": "same", "prompt": "one", "expected_substrings": ["one"]},
        {"id": "same", "prompt": "two", "expected_substrings": ["two"]},
    ]))
    with pytest.raises(ValueError, match="Duplicate"):
        ev.load_dataset(path)


def test_dataset_rejects_empty_prompt(tmp_path):
    path = tmp_path / "cases.json"
    path.write_text(json.dumps([{"id": "a", "prompt": " ", "expected_substrings": ["x"]}]))
    with pytest.raises(ValueError, match="prompt"):
        ev.load_dataset(path)


def test_dataset_rejects_case_with_no_assertions(tmp_path):
    path = tmp_path / "cases.json"
    path.write_text(json.dumps([{"id": "no-assert", "prompt": "What is 2+2?"}]))
    with pytest.raises(ValueError, match="defines no assertions"):
        ev.load_dataset(path)


def test_dataset_rejects_empty_or_whitespace_substrings(tmp_path):
    for bad_sub in ("", "   "):
        path = tmp_path / "cases.json"
        path.write_text(json.dumps([{"id": "a", "prompt": "hi", "expected_substrings": [bad_sub]}]))
        with pytest.raises(ValueError, match="cannot contain empty or whitespace-only strings"):
            ev.load_dataset(path)


def test_dataset_rejects_empty_or_whitespace_json_keys(tmp_path):
    path = tmp_path / "cases.json"
    path.write_text(json.dumps([{"id": "a", "prompt": "hi", "expected_json_keys": []}]))
    with pytest.raises(ValueError, match="cannot be empty when specified"):
        ev.load_dataset(path)

    path.write_text(json.dumps([{"id": "a", "prompt": "hi", "expected_json_keys": ["  "]}]))
    with pytest.raises(ValueError, match="cannot contain empty or whitespace-only keys"):
        ev.load_dataset(path)


def test_check_response_fails_when_no_assertions_defined():
    result = ev.check_response({"id": "none", "prompt": "test"}, "arbitrary output")
    assert result["passed"] is False
    assert any("no assertions" in f for f in result["failures"])


def test_substring_check_is_case_insensitive():
    result = ev.check_response(
        {"expected_substrings": ["paris", "FRANCE"]},
        "PARIS is the capital of France.",
    )
    assert result["passed"] is True
    assert result["failures"] == []


def test_missing_expected_substring_fails():
    result = ev.check_response(
        {"expected_substrings": ["Paris"]}, "London"
    )
    assert result["passed"] is False
    assert "Paris" in result["failures"][0]


def test_json_validation_and_required_keys():
    case = {"expected_json": True, "expected_json_keys": ["status"]}
    assert ev.check_response(case, '{"status":"ok"}')["passed"] is True
    assert ev.check_response(case, "not json")["passed"] is False
    assert ev.check_response(case, '{"other":1}')["passed"] is False


def test_post_json_handles_http_error(monkeypatch):
    def fake_urlopen(*args, **kwargs):
        raise urllib.error.HTTPError("http://test", 500, "Internal Server Error", {}, io.BytesIO(b""))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(RuntimeError, match="HTTP 500"):
        ev.post_json("http://localhost:11434/api/generate", {}, timeout=5)


def test_post_json_handles_unexpected_response_format(monkeypatch):
    class FakeResponse:
        def read(self):
            return b'["not a dict"]'
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    monkeypatch.setattr(urllib.request, "urlopen", lambda *args, **kwargs: FakeResponse())
    with pytest.raises(RuntimeError, match="unexpected response format"):
        ev.post_json("http://localhost:11434/api/generate", {}, timeout=5)


def test_evaluate_case_uses_mocked_ollama(monkeypatch):
    def fake_post(url, payload, timeout):
        assert url == "http://localhost:11434/api/generate"
        assert payload["model"] == "fake-model"
        return {
            "response": "Paris",
            "eval_count": 5,
            "eval_duration": 1_000_000_000,
            "prompt_eval_count": 10,
        }

    monkeypatch.setattr(ev, "post_json", fake_post)
    result = ev.evaluate_case(
        {"id": "capital", "prompt": "capital?", "expected_substrings": ["Paris"]},
        "fake-model",
        "http://localhost:11434",
        10,
        0.0,
    )
    assert result["status"] == "PASS"
    assert result["tokens_per_second"] == 5.0


def test_evaluate_case_captures_api_errors(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("unavailable")

    monkeypatch.setattr(ev, "post_json", fail)
    result = ev.evaluate_case(
        {"id": "x", "prompt": "hi", "expected_substrings": ["hi"]},
        "model",
        "http://localhost:11434",
        1,
        0.0,
    )
    assert result["status"] == "ERROR"
    assert result["passed"] is False


def test_summary_counts():
    summary = ev.summarize([
        {"status": "PASS", "latency_seconds": 1.0, "tokens_per_second": 10.0},
        {"status": "FAIL", "latency_seconds": 3.0, "tokens_per_second": 20.0},
        {"status": "ERROR", "latency_seconds": 2.0, "tokens_per_second": None},
    ])
    assert summary["total"] == 3
    assert summary["passed"] == 1
    assert summary["failed"] == 1
    assert summary["errors"] == 1
    assert summary["pass_rate"] == pytest.approx(1 / 3, abs=1e-4)
    assert summary["median_latency_seconds"] == 2.0


def test_run_evaluation_multiple_models(monkeypatch):
    def fake_eval(case, model, host, timeout, temperature):
        return {
            "id": case["id"], "model": model, "status": "PASS",
            "latency_seconds": 1.0, "tokens_per_second": 5.0,
            "passed": True, "failures": [], "response": "ok",
        }

    monkeypatch.setattr(ev, "evaluate_case", fake_eval)
    report = ev.run_evaluation(
        [{"id": "one", "prompt": "hi", "expected_substrings": ["hi"]}],
        ["model-a", "model-b"],
        "localhost:11434",
    )
    assert report["models"] == ["model-a", "model-b"]
    assert report["summary_by_model"]["model-a"]["passed"] == 1
    assert len(report["results"]) == 2


def test_main_cli_exit_code_0_and_no_save_responses(monkeypatch, tmp_path):
    dataset_file = tmp_path / "test_cases.json"
    dataset_file.write_text(json.dumps([
        {"id": "c1", "prompt": "say hello", "expected_substrings": ["hello"]}
    ]))
    output_file = tmp_path / "report.json"

    def fake_post(url, payload, timeout):
        return {"response": "hello world", "eval_count": 2, "eval_duration": 1_000_000_000}

    monkeypatch.setattr(ev, "post_json", fake_post)

    code = ev.main([
        "--dataset", str(dataset_file),
        "--models", "m1",
        "--output", str(output_file),
        "--no-save-responses",
    ])
    assert code == 0
    report_data = json.loads(output_file.read_text())
    assert report_data["results"][0]["status"] == "PASS"
    assert report_data["results"][0]["response"] is None


def test_main_cli_exit_code_1_on_failed_test(monkeypatch, tmp_path):
    dataset_file = tmp_path / "test_cases.json"
    dataset_file.write_text(json.dumps([
        {"id": "c1", "prompt": "say hello", "expected_substrings": ["bye"]}
    ]))
    output_file = tmp_path / "report.json"

    def fake_post(url, payload, timeout):
        return {"response": "hello world", "eval_count": 2, "eval_duration": 1_000_000_000}

    monkeypatch.setattr(ev, "post_json", fake_post)

    code = ev.main([
        "--dataset", str(dataset_file),
        "--models", "m1",
        "--output", str(output_file),
    ])
    assert code == 1


def test_main_cli_exit_code_2_on_invalid_host_or_dataset(tmp_path):
    dataset_file = tmp_path / "bad_cases.json"
    dataset_file.write_text(json.dumps([{"id": "bad", "prompt": "no assertions"}]))

    code = ev.main(["--dataset", str(dataset_file)])
    assert code == 2

    # Malformed host URL
    valid_dataset = Path(__file__).resolve().parent.parent / "examples" / "cases.json"
    code_bad_host = ev.main(["--dataset", str(valid_dataset), "--host", "http://"])
    assert code_bad_host == 2


def test_main_cli_exit_code_2_on_unwritable_output(monkeypatch, tmp_path):
    example_path = Path(__file__).resolve().parent.parent / "examples" / "cases.json"
    unwritable_output = "/nonexistent_dir/readonly_sub/report.json"

    def fake_eval(*args, **kwargs):
        return {"id": "x", "model": "m", "status": "PASS", "latency_seconds": 0.1, "tokens_per_second": 10, "passed": True, "failures": []}

    monkeypatch.setattr(ev, "evaluate_case", fake_eval)

    code = ev.main([
        "--dataset", str(example_path),
        "--output", unwritable_output,
    ])
    assert code == 2
