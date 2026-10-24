"""The core toolkit must work with no network and must not print or log prompt contents."""

import logging
import socket
from pathlib import Path

import pytest

from prompt_enhancer import analyze, enhance
from prompt_enhancer.evaluation import load_cases, run_offline

FIXTURES = Path(__file__).parent / "fixtures" / "prompts.jsonl"


@pytest.fixture
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("network access attempted")
    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


def test_analyze_enhance_and_eval_run_offline(no_network):
    analyze("Extract names and return JSON.", model="gemini")
    enhance("Draft a reply. Keep it under 50 words.", model="claude-sonnet-5")
    assert run_offline(load_cases(FIXTURES)).summary["failed"] == 0


def test_library_does_not_print_or_log_prompts(capsys, caplog):
    secret_text = "PROJECT-NIGHTINGALE launch plan. Keep it under 50 words."
    with caplog.at_level(logging.DEBUG):
        enhance(secret_text, model="gpt-4.1")
        analyze(secret_text)
    captured = capsys.readouterr()
    assert "NIGHTINGALE" not in captured.out + captured.err
    assert "NIGHTINGALE" not in caplog.text
