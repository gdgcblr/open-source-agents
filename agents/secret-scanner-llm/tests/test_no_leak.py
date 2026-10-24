"""Raw secrets must not appear in LLM prompts, logs, reports, JSON or exceptions."""

import json
import logging

import pytest

from secret_scanner import report
from secret_scanner.llm import MalformedResponse, OllamaClient
from secret_scanner.scanner import scan

from . import helpers as H

SECRETS = [H.aws(), H.github(), H.stripe(), H.google(), H.slack(), H.password(), "Vq83nKd02Lx",
           H.PEM_BODY]


def make_repo(tmp_path):
    src = "\n".join([
        f'AWS = "{H.aws()}"', f"export GH={H.github()}", f'S = "{H.stripe()}"',
        f'G = "{H.google()}"', f"SLACK={H.slack()}", f'password = "{H.password()}"',
        f'DB = "{H.db_url()}"', H.pem_header(), H.PEM_BODY, "-----END RSA PRIVATE KEY-----",
    ])
    (tmp_path / "leaky.py").write_text(src)
    return tmp_path


def assert_clean(blob: str):
    for s in SECRETS:
        assert s not in blob
        # also the sensitive tail of each secret
        assert s[len(s) // 2:] not in blob


def test_prompts_logs_reports_are_clean(tmp_path, caplog):
    make_repo(tmp_path)
    cap = []
    cl = OllamaClient(transport=H.make_ollama_transport([H.verdict("real", 0.9, "looks real")], cap))
    with caplog.at_level(logging.DEBUG):
        r = scan(tmp_path, client=cl)
    assert len(cap) >= 7
    assert_clean(json.dumps(cap))
    assert_clean(caplog.text)
    assert_clean(report.to_json(r))
    assert_clean(report.to_markdown(r))


def test_no_llm_report_is_clean(tmp_path):
    make_repo(tmp_path)
    r = scan(tmp_path, use_llm=False)
    assert r.reportable
    assert_clean(report.to_json(r))
    assert_clean(report.to_markdown(r))


def test_exceptions_are_clean(tmp_path):
    make_repo(tmp_path)
    cl = OllamaClient(transport=H.make_ollama_transport(["nope"]), max_retries=0)
    from secret_scanner.scanner import collect_candidates
    cands, _ = collect_candidates(tmp_path)
    with pytest.raises(MalformedResponse) as e:
        cl.triage(cands[0])
    assert_clean(repr(e.value) + str(e.value))


def test_malformed_llm_output_does_not_break_scan(tmp_path):
    make_repo(tmp_path)
    cl = OllamaClient(transport=H.make_ollama_transport(["junk"]), max_retries=0)
    r = scan(tmp_path, client=cl)
    assert r.reportable and all(f.verdict == "unverified" for f in r.findings)
    assert_clean(report.to_json(r))
