"""Live progress lines: what the CLI prints while a scan runs."""

from __future__ import annotations

import json

import pytest

from rce_sentinel import cli
from rce_sentinel.engine import FileSet
from rce_sentinel.trace import live_printer

from .conftest import seed_osv  # noqa: F401
from .test_router import LINES, finding, make_router, v

CODE = ("import os\nfrom flask import request\n\n\ndef ping():\n"
        "    host = request.args.get('host')\n    os.system('ping ' + host)\n")


def test_router_emits_each_step(settings) -> None:
    r, _ = make_router(settings, {"judge:tier1": [v("vulnerable", 0.4)],
                                  "judge:tier2": [v("vulnerable", 0.95)]})
    lines: list[str] = []
    r.emit = lines.append
    r.judge(finding(), LINES)
    text = "\n".join(lines)
    assert "* judging py-os-system at line 2" in text
    assert "-> judge: asking apple-foundationmodel (mock)" in text
    assert "<- apple-foundationmodel (mock) answered in" in text
    assert "escalated: confidence 0.40" in text and "accepted vulnerable" in text
    assert "-> verify: asking" in text


def test_degrade_notices_are_printed_live(settings) -> None:
    r, _ = make_router(settings, {})
    lines: list[str] = []
    r.emit = lines.append
    r._degrade("model fallback (token quota reached): x")
    assert lines == ["  ! model fallback (token quota reached): x"]


def test_scanner_announces_tools_and_prerouter(scanner) -> None:
    lines: list[str] = []
    scanner.emit = lines.append
    scanner.scan(FileSet({"a.py": CODE}), "trace")
    text = "\n".join(lines)
    assert "[tools] rules/AST: 1 sink hit(s); taint tracer: 1 source-to-sink path(s)" in text
    assert "[pre-router] 1 finding(s) need a model" in text
    assert "* judging py-os-system" in text


def test_live_printer_stamps_seconds(capsys: pytest.CaptureFixture[str]) -> None:
    live_printer()("hello")
    out = capsys.readouterr().out
    assert out.startswith("[") and "s] hello" in out


def test_trace_cli_prints_live_log_then_summary(tmp_path, capsys: pytest.CaptureFixture[str]
                                                 ) -> None:
    f = tmp_path / "p.py"
    f.write_text(CODE)
    assert cli.main(["trace", "--file", str(f), "--state", str(tmp_path / "st")]) == 0
    out = capsys.readouterr().out
    assert out.index("scanning snippet.py") < out.index("-> judge: asking") < out.index("SUMMARY")
    assert "[7] VERDICT" in out and "py-os-system" in out
    cli.main(["trace", "--file", str(f), "--state", str(tmp_path / "st2"), "--no-live"])
    quiet = capsys.readouterr().out
    assert "-> judge: asking" not in quiet and "[7] VERDICT" in quiet


def test_scan_live_goes_to_stderr_and_keeps_json_clean(repo, capsys: pytest.CaptureFixture[str]
                                                       ) -> None:
    cli.main(["--repo", str(repo), "scan", "--json", "--live"])
    cap = capsys.readouterr()
    json.loads(cap.out)  # stdout is still pure JSON
    assert "[tools]" in cap.err and "[pre-router]" in cap.err
