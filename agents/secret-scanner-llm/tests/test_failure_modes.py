"""Failure-mode tests. Principle: FAIL CLOSED - an LLM/infra failure never reduces findings."""

import json

import httpx
import pytest

from secret_scanner import report
from secret_scanner.llm import OllamaClient, OllamaTimeout
from secret_scanner.scanner import scan

from . import helpers as H


def repo(tmp_path, n=3):
    for i in range(n):
        (tmp_path / f"f{i}.py").write_text(f'password = "{H.password()}{i}"\n')
    return tmp_path


def baseline_count(p):
    return len(scan(p, use_llm=False).reportable)


def test_ollama_down_falls_back_with_warning_and_keeps_findings(tmp_path):
    repo(tmp_path)
    r = scan(tmp_path, host="http://127.0.0.1:9")
    assert r.stats["mode"] == "no-llm" and any("fell back" in w for w in r.warnings)
    assert len(r.reportable) == baseline_count(tmp_path) == 3 and r.exit_code == 1
    assert "WARNING" in report.to_markdown(r)


def test_model_not_pulled_falls_back(tmp_path):
    repo(tmp_path)
    cl = OllamaClient(model="gemma3:27b", transport=H.make_ollama_transport([{}], tags=("gemma4:e2b-it-q4_K_M",)))
    r = scan(tmp_path, client=cl)
    assert r.stats["mode"] == "no-llm" and "ollama pull gemma3:27b" in " ".join(r.warnings)
    assert len(r.reportable) == 3


def test_require_llm_raises(tmp_path):
    from secret_scanner.llm import OllamaUnavailable
    repo(tmp_path)
    with pytest.raises(OllamaUnavailable):
        scan(tmp_path, host="http://127.0.0.1:9", fallback_to_no_llm=False)


def test_timeout_retries_with_backoff_then_unverified(tmp_path):
    repo(tmp_path, 1)
    calls, sleeps = [], []

    def handler(req):
        if req.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "gemma4:e2b-it-q4_K_M"}]})
        calls.append(1)
        raise httpx.ReadTimeout("slow")

    cl = OllamaClient(transport=httpx.MockTransport(handler), max_retries=2, sleep=sleeps.append)
    r = scan(tmp_path, client=cl)
    assert len(calls) == 3 and sleeps == [0.5, 1.0]  # bounded retries, exponential backoff
    assert r.findings[0].verdict == "unverified" and r.exit_code == 1 and cl.timeouts == 3


def test_timeout_then_success(tmp_path):
    repo(tmp_path, 1)
    state = {"n": 0}

    def handler(req):
        if req.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "gemma4:e2b-it-q4_K_M"}]})
        state["n"] += 1
        if state["n"] == 1:
            raise httpx.ReadTimeout("slow")
        return httpx.Response(200, json={"message": {"content": json.dumps(H.verdict("placeholder", 0.9))}})

    r = scan(tmp_path, client=OllamaClient(transport=httpx.MockTransport(handler), sleep=lambda s: None))
    assert r.findings[0].verdict == "placeholder"


def test_malformed_json_keeps_finding_unverified(tmp_path):
    repo(tmp_path)
    cl = OllamaClient(transport=H.make_ollama_transport(['{"verdict": "banana"}']), max_retries=1)
    r = scan(tmp_path, client=cl)
    assert len(r.reportable) == 3 and {f.verdict for f in r.findings} == {"unverified"}
    assert cl.invalid_json == 6 and r.exit_code == 1


def test_hallucinated_verdict_or_low_confidence_needs_review(tmp_path):
    repo(tmp_path, 1)
    r = scan(tmp_path, client=OllamaClient(transport=H.make_ollama_transport([H.verdict("false_positive", 0.3)])))
    f = r.findings[0]
    assert f.verdict == "uncertain" and "NEEDS HUMAN REVIEW" in f.llm_note and r.exit_code == 1


def test_llm_dies_midrun_remaining_unverified(tmp_path):
    repo(tmp_path, 3)
    state = {"n": 0}

    def handler(req):
        if req.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "gemma4:e2b-it-q4_K_M"}]})
        state["n"] += 1
        if state["n"] == 1:
            return httpx.Response(200, json={"message": {"content": json.dumps(H.verdict("real"))}})
        raise httpx.ConnectError("gone")

    r = scan(tmp_path, client=OllamaClient(transport=httpx.MockTransport(handler)))
    assert len(r.findings) == 3 and len(r.reportable) == 3
    assert any("mid-run" in w for w in r.warnings)


def test_unexpected_exception_in_triage_fails_closed(tmp_path):
    from secret_scanner.scanner import collect_candidates
    from secret_scanner.triage import triage_all
    cands, _ = collect_candidates(repo(tmp_path))

    def boom(c):
        raise ZeroDivisionError

    out = triage_all(cands, boom)
    assert len(out) == 3 and all(f.verdict == "unverified" for f in out)


def test_candidate_cap_reports_truncation(tmp_path):
    repo(tmp_path, 5)
    cl = OllamaClient(transport=H.make_ollama_transport([H.verdict("placeholder", 0.99)]))
    r = scan(tmp_path, client=cl, max_llm_candidates=2)
    assert sum(f.verdict == "placeholder" for f in r.findings) == 2
    assert sum(f.verdict == "unverified" for f in r.findings) == 3 and r.exit_code == 1
    assert any("Candidate cap" in w for w in r.warnings)


def test_skips_are_counted_in_report(tmp_path):
    (tmp_path / "bin.dat").write_bytes(b"\x00\x01\x02")
    (tmp_path / "big.txt").write_text("a" * 1_000_001)
    (tmp_path / "real").write_text("x")
    (tmp_path / "link").symlink_to(tmp_path / "real")
    r = scan(tmp_path, use_llm=False)
    s = r.stats
    assert s["skipped_binary"] == 1 and s["skipped_too_large"] == 1 and s["skipped_symlink"] == 1
    md = report.to_markdown(r)
    assert "binary=1" in md and "too_large=1" in md


def test_unreadable_file_makes_scan_incomplete_nonzero(tmp_path):
    f = tmp_path / "locked.py"
    f.write_text("x = 1")
    f.chmod(0)
    try:
        r = scan(tmp_path, use_llm=False)
    finally:
        f.chmod(0o644)
    import os
    if os.geteuid() == 0:
        pytest.skip("root can read anything")
    assert r.incomplete and r.exit_code == 2 and any("INCOMPLETE" in w for w in r.warnings)


def test_one_bad_file_does_not_abort_scan(tmp_path, monkeypatch):
    (tmp_path / "a.py").write_text(f'password = "{H.password()}"\n')
    (tmp_path / "b.py").write_text("x=1\n")
    import secret_scanner.scanner as S
    real = S.scan_text

    def flaky(rel, text):
        if rel == "b.py":
            raise RuntimeError("parser crash")
        return real(rel, text)

    monkeypatch.setattr(S, "scan_text", flaky)
    r = scan(tmp_path, use_llm=False)
    assert len(r.reportable) == 1 and r.stats["errors"] == 1 and r.exit_code == 1


def test_exit_code_matrix(tmp_path):
    clean = tmp_path / "clean"
    clean.mkdir()
    (clean / "x.py").write_text("x = 1\n")
    assert scan(clean, use_llm=False).exit_code == 0
    d = repo(tmp_path / "d" if (tmp_path / "d").mkdir() is None else tmp_path, 1)
    assert scan(d, use_llm=False).exit_code == 1


def test_timeout_class():
    assert issubclass(OllamaTimeout, Exception)
