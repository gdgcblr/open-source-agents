import json
import os
import subprocess
import sys
from argparse import Namespace
from pathlib import Path

from prompt_enhancer.cli import interactive_review

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "prompts.jsonl"


def cli(*args, stdin=None, cwd=None):
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    return subprocess.run([sys.executable, "-m", "prompt_enhancer", *args], input=stdin, capture_output=True, text=True, env=env, cwd=cwd)


P = "Write a function that removes duplicate users from a list. Keep it under 30 lines."


def test_analyze_text_json_sarif_and_stdin(tmp_path):
    t = cli("analyze", P)
    assert t.returncode == 0 and "PE401" in t.stdout and "Locked requirements" in t.stdout
    j = json.loads(cli("analyze", "--format", "json", "-", stdin=P).stdout)
    assert j["task_type"] == "coding" and any(d["rule_id"] == "PE401" for d in j["diagnostics"])
    f = tmp_path / "p.txt"
    f.write_text(P)
    s = json.loads(cli("analyze", "--input", str(f), "--format", "sarif").stdout)
    res = s["runs"][0]["results"]
    assert s["version"] == "2.1.0" and res and res[0]["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] == str(f)


def test_analyze_fail_on_threshold():
    assert cli("analyze", "--fail-on", "warning", P).returncode == 1
    assert cli("analyze", "--fail-on", "error", P).returncode == 0


def test_enhance_diff_output_json_and_answers(tmp_path):
    d = cli("enhance", "-m", "claude-sonnet-5", "--diff", "--accept", "S.wrap,S.constraints", P)
    assert d.returncode == 0 and d.stdout.startswith("--- original") and "status: enhanced" in d.stderr
    out = tmp_path / "enhanced.txt"
    cli("enhance", "-m", "gemini", "-o", str(out), "--answer", "PE401=Python 3.12", P)
    assert "Language/runtime: Python 3.12" in out.read_text() and P.split(".")[0] in out.read_text()
    j = json.loads(cli("enhance", "--format", "json", P).stdout)
    assert j["status"] == "no-change" and {"S.wrap", "S.constraints", "PE401.1"} <= set(j["pending"])


def test_enhance_bad_answer_format_is_usage_error():
    r = cli("enhance", "--answer", "no-equals-sign", P)
    assert r.returncode != 0 and "ID=TEXT" in r.stderr


def test_interactive_review_with_scripted_answers():
    def ask(question):
        if "[S.wrap]" in question:
            return "y"
        if "Which language" in question:
            return "Python 3.12"
        return ""

    args = Namespace(model="claude-sonnet-5", harness="api", min_words=None, force=False, disable=None, min_confidence=None)
    accept, reject, answers = interactive_review(P, args, ask=ask)
    assert accept == ["S.wrap"] and reject == []
    assert answers == {"PE401.1": "Python 3.12"}


def test_eval_command_baseline_and_exit_codes(tmp_path):
    save = tmp_path / "base.json"
    r = cli("eval", "--dataset", str(FIXTURES), "--save", str(save))
    assert r.returncode == 0 and "0 failed" in r.stdout
    r2 = cli("eval", "--dataset", str(FIXTURES), "--baseline", str(save), "--format", "markdown")
    assert r2.returncode == 0 and "Regressions vs baseline | 0" in r2.stdout
    bad = tmp_path / "bad.jsonl"
    bad.write_text('{"id": "x", "prompt": "Why?", "expect": {"rules": ["PE101"]}}\n')
    assert cli("eval", "--dataset", str(bad)).returncode == 1
    bad.write_text("{oops\n")
    assert cli("eval", "--dataset", str(bad)).returncode == 2


def test_eval_e2e_mock_runs_without_keys():
    r = cli("eval-e2e", "--dataset", str(ROOT / "examples" / "e2e_cases.jsonl"), "--provider", "mock", "--model", "m")
    assert r.returncode == 0 and "MOCK provider" in r.stdout


def test_eval_e2e_real_provider_without_key_fails_cleanly():
    r = cli("eval-e2e", "--dataset", str(ROOT / "examples" / "e2e_cases.jsonl"), "--provider", "anthropic", "--model", "claude-sonnet-5")
    assert r.returncode == 2 and "ANTHROPIC_API_KEY" in r.stderr


def test_profiles_rules_resolve():
    assert "anthropic-claude" in cli("profiles").stdout
    assert "PE701" in cli("rules").stdout
    res = json.loads(cli("resolve", "claude-opus-4-6").stdout)
    assert res["profile"] == "anthropic-claude" and res["variant"] == "claude-opus-4.5-4.6"


def test_unknown_harness_is_a_clean_error():
    r = cli("enhance", "--harness", "nope", P)
    assert r.returncode == 2 and "unknown harness" in r.stderr


def test_hook_subcommand():
    payload = json.dumps({"hook_event_name": "UserPromptSubmit", "prompt": "Refactor the cache module. Keep the public API unchanged."})
    r = subprocess.run([sys.executable, "-m", "prompt_enhancer", "hook", "claude-code"], input=payload, capture_output=True, text=True,
                       env={**os.environ, "PYTHONPATH": str(ROOT / "src"), "PROMPT_ENHANCER_RESTATE": "1"})
    assert r.returncode == 0 and json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
