import json
from xml.etree import ElementTree as ET

from helpers import scripted_cfg, scripted_matrix

from murphy import report
from murphy.checks import build_checks
from murphy.config.schema import FailIf
from murphy.core.ci import evaluate
from murphy.replay import replay
from murphy.targets import build_target


async def test_all_reports_from_matrix(tmp_path):
    await scripted_matrix(tmp_path)
    data = report.write_all(tmp_path)
    for name in report.OUTPUTS:
        assert (tmp_path / name).exists(), name

    assert data["totals"]["completion"] == 0.5 and data["totals"]["labels"] == {"dup": 1}
    results = json.loads((tmp_path / "results.json").read_text())
    assert results["schema_version"] == 1 and len(results["runs"]) == 2
    assert {"persona", "fault", "passed", "labels", "checks", "cell"} <= set(results["runs"][0])

    suite = ET.fromstring((tmp_path / "junit.xml").read_text())
    assert suite.get("tests") == "2" and suite.get("failures") == "1"
    assert suite.find("testcase[@name='timeout']/failure").get("message") == "dup"

    md = (tmp_path / "report.md").read_text()
    assert "completion        1/2 (50%)" in md and "⚡ TIMEOUT (injected, but committed)" in md
    assert "single-booking" in md

    term = report.terminal(data)
    assert "FAIL dup" in term and "PASS" in term


async def test_html_is_self_contained_and_escapes_trace_text(tmp_path):
    await scripted_matrix(tmp_path)
    # Inject a hostile agent reply into the recorded trace.
    trace = tmp_path / "cooperative__timeout" / "trace.jsonl"
    lines = trace.read_text().splitlines()
    lines.append(json.dumps({"v": 1, "kind": "agent", "ts": 9e9, "seq": 99, "text": "</script><script>alert(1)</script>"}))
    trace.write_text("\n".join(lines) + "\n")
    report.write_all(tmp_path)
    page = (tmp_path / "report.html").read_text()
    assert "__MURPHY_DATA__" not in page
    assert "<script>alert(1)</script>" not in page
    assert "http://" not in page and "https://" not in page  # no external assets
    assert '"schema_version": 1' in page


async def test_replays_attach_to_their_source_cell(tmp_path):
    cfg, _ = await scripted_matrix(tmp_path)
    await replay(cfg, tmp_path / "cooperative__timeout",
                 build_target(cfg.target, "scripted_agents:fixed_policy"), build_checks(cfg.checks))
    data = report.write_all(tmp_path)
    assert len(data["runs"]) == 2
    cell = next(r for r in data["runs"] if r["cell"] == "cooperative__timeout")
    assert len(cell["replays"]) == 1 and cell["replays"][0]["result"]["passed"]


def test_ci_thresholds():
    totals = {"completion": 0.5, "labels": {"dup": 1}}
    assert evaluate(totals, FailIf()) == []
    tripped = evaluate(totals, FailIf(completion_below=0.8, any_label=["dup", "quit"]))
    assert tripped == ["completion 50% < 80%", "1 run(s) labelled 'dup'"]
