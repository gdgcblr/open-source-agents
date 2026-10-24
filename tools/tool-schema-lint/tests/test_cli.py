import json
import subprocess
import sys

import pytest
from conftest import EXAMPLES, PROJECT_DIR

from tool_schema_lint.cli import main
from tool_schema_lint.rules import REGISTRY

BROKEN = str(EXAMPLES / "calendar_mcp_broken.json")
FIXED = str(EXAMPLES / "calendar_mcp_fixed.json")
OPENAI = str(EXAMPLES / "openai_strict_tools.json")


def run(capsys, *args):
    code = main(list(args))
    out = capsys.readouterr()
    return code, out.out, out.err


def findings(capsys, *args):
    code, out, _ = run(capsys, *args, "--format", "json")
    return code, json.loads(out)


def test_fixed_example_is_clean_for_all_targets(capsys):
    code, doc = findings(capsys, FIXED, "--target", "all")
    assert code == 0
    assert doc["summary"] == {"errors": 0, "warnings": 0, "info": 0}
    assert doc["files"][0]["targets"] == ["anthropic", "gemini", "mcp", "openai", "openai-strict"]


def test_broken_example_default_mcp_target(capsys):
    code, doc = findings(capsys, BROKEN)
    assert code == 1
    rules = sorted(f["rule"] for f in doc["files"][0]["findings"])
    assert rules == ["G005", "G005", "G008", "G011", "G013", "G014", "G015", "M002"]


def test_broken_example_provider_targets(capsys):
    _, doc = findings(capsys, BROKEN, "-t", "gemini", "-t", "openai", "-t", "anthropic")
    rules = {f["rule"] for f in doc["files"][0]["findings"]}
    assert {"GM002", "GM003", "GM004", "GM005", "O001", "A001", "A002"} <= rules
    assert doc["summary"]["errors"] == 9


def test_openai_example_strict_errors(capsys):
    code, doc = findings(capsys, OPENAI)
    assert code == 1
    assert [f["rule"] for f in doc["files"][0]["findings"]] == ["S001", "S002"]


@pytest.mark.parametrize("fail_on, expected", [("never", 0), ("error", 1), ("warning", 1), ("info", 1)])
def test_fail_on_levels(capsys, fail_on, expected):
    assert run(capsys, BROKEN, "--fail-on", fail_on)[0] == expected


def test_warnings_only_pass_by_default(capsys):
    code, _, _ = run(capsys, BROKEN, "--disable", "G008,G015")
    assert code == 0
    assert run(capsys, BROKEN, "--disable", "G008", "--disable", "g015", "--fail-on", "warning")[0] == 1


def test_text_output_shape(capsys):
    _, out, _ = run(capsys, BROKEN)
    assert "weather.get-forecast" in out
    assert "error   G008   /result/tools/0/inputSchema/required" in out
    assert out.rstrip().endswith("2 errors, 5 warnings, 1 info")


def test_github_annotations(capsys):
    _, out, _ = run(capsys, OPENAI, "--format", "github")
    lines = out.strip().splitlines()
    assert lines[0].startswith("::error file=") and "title=S001 lookup_order::" in lines[0]
    assert lines[-1] == "tool-schema-lint: 2 errors, 0 warnings, 0 info"


def test_max_tokens_budget(capsys):
    code, doc = findings(capsys, FIXED, "--max-tokens", "100")
    assert code == 1 and doc["files"][0]["findings"][0]["rule"] == "G016"


def test_list_rules_lists_every_rule(capsys):
    code, out, _ = run(capsys, "--list-rules")
    assert code == 0
    for rule_id in REGISTRY:
        assert f"\n{rule_id} " in "\n" + out


@pytest.mark.parametrize("args, message", [
    ([], "no input files"),
    (["missing.json"], "file not found"),
    ([FIXED, "--disable", "X999"], "unknown rule id"),
    ([FIXED, "--max-tokens", "0"], "positive integer"),
])
def test_usage_errors_exit_2(capsys, args, message):
    code, _, err = run(capsys, *args)
    assert code == 2 and message in err


def test_invalid_json_exit_2(capsys, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{ not json", encoding="utf-8")
    code, _, err = run(capsys, str(bad))
    assert code == 2 and "invalid JSON" in err


def test_multiple_files(capsys):
    _, doc = findings(capsys, FIXED, OPENAI)
    assert [f["file"] for f in doc["files"]] == [FIXED, OPENAI]
    assert doc["summary"]["errors"] == 2


def test_module_entry_point_with_stdin():
    """End to end: run the real interpreter, pipe a file through stdin."""
    with open(OPENAI, "rb") as fh:
        proc = subprocess.run([sys.executable, "-m", "tool_schema_lint", "-", "--format", "json"],
                              stdin=fh, capture_output=True, check=False, cwd=PROJECT_DIR, timeout=60)
    assert proc.returncode == 1, proc.stderr
    doc = json.loads(proc.stdout)
    assert doc["files"][0]["file"] == "<stdin>"
    assert doc["summary"]["errors"] == 2
