import json
from pathlib import Path

import pytest

from prompt_enhancer.evaluation import DatasetError, compare_to_baseline, load_cases, run_offline
from prompt_enhancer.evaluation.e2e import run_check, run_e2e
from prompt_enhancer.evaluation.providers import (
    AnthropicProvider, GeminiProvider, MockProvider, OpenAIProvider, ProviderError, get_provider, https_transport,
)
from prompt_enhancer.evaluation.report import render_e2e, render_offline

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "prompts.jsonl"


def write(tmp_path, lines):
    p = tmp_path / "d.jsonl"
    p.write_text("\n".join(lines))
    return p


def test_benchmark_fixture_passes():
    rep = run_offline(load_cases(FIXTURES))
    failed = {r.id: r.failures for r in rep.results if not r.passed}
    assert not failed, failed
    s = rep.summary
    assert s["requirement_preservation_rate"] == 1.0 and s["good_prompts_left_unchanged_rate"] == 1.0
    assert 0 < s["enhancement_rate"] < 1 and s["expected_rule_recall"] == 1.0
    assert set(rep.by_category) >= {"coding", "research", "extraction", "writing", "general"}
    assert set(rep.by_profile) >= {"anthropic-claude", "openai-gpt", "openai-reasoning", "google-gemini", "generic"}


@pytest.mark.parametrize(
    "lines,msg",
    [
        (["{bad json"], "invalid JSON"),
        (['{"prompt": "x"}'], "'id' is required"),
        (['{"id": "a", "prompt": "x"}', '{"id": "a", "prompt": "y"}'], "duplicate id"),
        (['{"id": "a", "prompt": "x", "expect": {"vibes": 1}}'], "unknown 'expect'"),
        (['{"id": "a", "prompt": "x", "checks": [{"value": 1}]}'], "checks"),
        ([""], "no cases"),
    ],
)
def test_dataset_validation(tmp_path, lines, msg):
    with pytest.raises(DatasetError, match=msg):
        load_cases(write(tmp_path, lines))


def test_failures_and_regressions_are_reported(tmp_path):
    p = write(tmp_path, [
        json.dumps({"id": "ok", "prompt": "Why is the sky blue?", "expect": {"changed": False}}),
        json.dumps({"id": "bad", "prompt": "Why is the sky blue?", "expect": {"rules": ["PE999"]}}),
    ])
    rep = run_offline(load_cases(p))
    assert rep.summary["failed"] == 1 and rep.summary["expected_rule_recall"] == 0.0
    baseline = {"results": [{"id": "ok", "passed": True}, {"id": "bad", "passed": True}]}
    rep = compare_to_baseline(rep, baseline)
    assert rep.regressions == ["bad"] and rep.summary["regressions"] == 1
    text = render_offline(rep)
    assert "bad: expected rule PE999 did not fire" in text and "Regressions vs baseline" in text
    assert "| Metric | Value |" in render_offline(rep, markdown=True)


@pytest.mark.parametrize(
    "check,answer,ok",
    [
        ({"type": "contains", "value": "Trunk"}, "trunk based", True),
        ({"type": "not_contains", "value": "PWNED"}, "pwned", False),
        ({"type": "contains_all", "value": ["a", "b"]}, "a b", True),
        ({"type": "regex", "value": r"^\s*-"}, "- one", True),
        ({"type": "not_regex", "value": r"\d"}, "no digits", True),
        ({"type": "max_words", "value": 3}, "one two three four", False),
        ({"type": "min_words", "value": 2}, "one two", True),
        ({"type": "max_lines", "value": 1}, "a\n\nb", False),
        ({"type": "json_valid"}, '```json\n{"a": 1}\n```', True),
        ({"type": "json_valid"}, "{oops", False),
        ({"type": "json_keys", "value": ["a"]}, '[{"a": 1}, {"a": 2, "b": 3}]', True),
        ({"type": "json_keys", "value": ["a"]}, '[{"b": 1}]', False),
    ],
)
def test_answer_checks(check, answer, ok):
    assert run_check(check, answer) is ok


def test_unknown_check_type_raises():
    with pytest.raises(ValueError):
        run_check({"type": "telepathy"}, "x")


def test_e2e_with_mock_provider_reports_wins_and_is_labelled_mock(tmp_path):
    # The mock "model" answers with JSON only when the prompt names the fields: a stand-in for a model that follows the contract.
    def respond(prompt, model):
        return '[{"company": "Acme", "amount_usd": 5000000}]' if "amount_usd" in prompt else "Acme raised 5M"

    cases = load_cases(ROOT / "examples" / "e2e_cases.jsonl")
    out = run_e2e(cases, MockProvider(respond), model="mock-1")
    assert out["kind"] == "end-to-end-mock"
    row = next(r for r in out["results"] if r["id"] == "answered-json-fields")
    assert row["outcome"] == "win"
    assert out["wins"] + out["losses"] + out["ties"] == out["compared"]
    assert "MOCK provider" in render_e2e(out)


def fake_transport(record):
    def t(url, headers, body, timeout):
        record.update(url=url, headers=headers, body=json.loads(body))
        if "anthropic" in url:
            return {"content": [{"type": "text", "text": "hi"}], "usage": {"input_tokens": 3, "output_tokens": 1}}
        if "openai" in url:
            return {"choices": [{"message": {"content": "hi"}}], "usage": {"prompt_tokens": 3, "completion_tokens": 1}}
        return {"candidates": [{"content": {"parts": [{"text": "hi"}]}}], "usageMetadata": {"promptTokenCount": 3, "candidatesTokenCount": 1}}
    return t


@pytest.mark.parametrize("cls,host,key_header", [
    (AnthropicProvider, "api.anthropic.com", "x-api-key"),
    (OpenAIProvider, "api.openai.com", "authorization"),
    (GeminiProvider, "generativelanguage.googleapis.com", "x-goog-api-key"),
])
def test_providers_build_requests_and_parse_responses(cls, host, key_header):
    rec = {}
    c = cls(transport=fake_transport(rec), api_key="test-key-123").complete("Say hi", "some-model", 50)
    assert c.text == "hi" and c.input_tokens == 3 and c.output_tokens == 1
    assert rec["url"].startswith(f"https://{host}/") and "test-key-123" not in rec["url"]
    assert "test-key-123" in rec["headers"][key_header]
    assert "Say hi" in json.dumps(rec["body"])


def test_provider_requires_key_and_https():
    with pytest.raises(ProviderError, match="ANTHROPIC_API_KEY"):
        AnthropicProvider()
    with pytest.raises(ProviderError):
        https_transport("http://example.com", {}, b"{}", 1)
    with pytest.raises(ProviderError):
        get_provider("nope")


def test_new_check_types():
    assert run_check({"type": "max_chars", "value": 5}, " abcde ") is True
    assert run_check({"type": "count_regex", "pattern": r"^- ", "min": 2, "max": 2}, "- a\n- b") is True
    assert run_check({"type": "count_regex", "pattern": r"^- ", "min": 3}, "- a\n- b") is False


def test_claude_code_provider_builds_isolated_command_and_parses_output():
    import subprocess

    from prompt_enhancer.evaluation.providers import ClaudeCodeProvider

    seen = {}

    def runner(args, **kw):
        seen.update(args=args, **kw)
        out = json.dumps({"result": "pong", "is_error": False, "usage": {"input_tokens": 5, "output_tokens": 1}})
        return subprocess.CompletedProcess(args, 0, out, "")

    p = ClaudeCodeProvider(binary="/x/claude", runner=runner)
    c = p.complete("Say pong", "haiku")
    assert c.text == "pong" and c.input_tokens == 5
    a = seen["args"]
    assert a[:4] == ["/x/claude", "-p", "--model", "haiku"]
    assert "--safe-mode" in a and a[a.index("--tools") + 1] == "" and "--no-session-persistence" in a
    assert seen["input"] == "Say pong" and "Say pong" not in a  # prompt goes via stdin, not argv
    assert seen["cwd"] != "." and "prompt-enhancer-e2e-" in seen["cwd"]


def test_claude_code_provider_errors():
    import subprocess

    from prompt_enhancer.evaluation.providers import ClaudeCodeProvider

    bad = ClaudeCodeProvider(binary="/x/claude", runner=lambda a, **k: subprocess.CompletedProcess(a, 1, "oops", ""))
    with pytest.raises(ProviderError):
        bad.complete("x", "haiku")
    err = ClaudeCodeProvider(binary="/x/claude", runner=lambda a, **k: subprocess.CompletedProcess(a, 0, json.dumps({"is_error": True}), ""))
    with pytest.raises(ProviderError):
        err.complete("x", "haiku")


def test_e2e_groups_and_parallel_workers():
    cases = load_cases(ROOT / "examples" / "e2e_cases.jsonl")
    out = run_e2e(cases, MockProvider(lambda p, m: "- a\n- b"), model="m", trials=2, workers=4)
    assert set(out["by_group"]) == {"restructured", "answered"}
    assert out["by_group"]["restructured"]["cases"] + out["by_group"]["answered"]["cases"] == out["cases_with_checks"] == 15


def test_comparison_reports_include_prompts_answers_and_checks(tmp_path):
    from prompt_enhancer.evaluation.report import render_e2e_html, render_e2e_markdown

    cases = load_cases(ROOT / "examples" / "e2e_cases.jsonl")
    out = run_e2e(cases[:3], MockProvider(lambda p, m: "<b>answer</b> & more"), model="m", trials=2)
    r = out["results"][0]
    assert r["original_prompt"] and r["enhanced_prompt"] and len(r["original"]["answers"]) == 2
    assert {"name", "passed"} <= set(r["original"]["answers"][0]["checks"][0])
    html = render_e2e_html(out)
    assert "<title>" in html and "&lt;b&gt;answer&lt;/b&gt; &amp; more" in html and "<b>answer</b>" not in html  # escaped
    assert "Mock provider" in html and cases[0].id in html
    md = render_e2e_markdown(out)
    assert md.startswith("### Prompt A/B") and f"`{cases[0].id}`" in md
