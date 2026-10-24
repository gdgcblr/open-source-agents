"""Nothing sensitive may leave the process: LLM prompt, report, ADK tool output."""
from types import SimpleNamespace

from triage.adapters.providers import GeminiProvider
from triage.adapters.report import render
from triage.models import Category, RunInput, TestFailure, Verdict
from triage.service import triage

EMAIL = "carol@corp.io"
IP = "10.9.8.7"


def make_failure():
    return TestFailure(name="test_x", message=f"user {EMAIL} not found at {IP}",
                       details=f"token=abcd1234efgh5678 for {EMAIL}")


class FakeClient:
    def __init__(self):
        self.prompts = []
        self.models = SimpleNamespace(generate_content=self._gen)

    def _gen(self, model, contents, config):
        self.prompts.append(contents)
        return SimpleNamespace(text='{"category":"UNKNOWN","confidence":0.2,"evidence":["saw ' + EMAIL + '"],"suggested_action":"call ' + IP + '"}')


def test_gemini_prompt_is_redacted_before_leaving():
    client = FakeClient()
    v = GeminiProvider(client=client).classify(make_failure(), [f"log line {EMAIL} {IP}"])
    sent = client.prompts[0]
    assert EMAIL not in sent and IP not in sent and "abcd1234efgh5678" not in sent
    assert EMAIL not in " ".join(v.evidence) and IP not in v.suggested_action  # model output redacted too


def test_report_is_redacted_and_shows_counts_only():
    run = RunInput(failures=[make_failure()], total_tests=1, log_lines=[f"{EMAIL} {IP}"])
    result = triage(run, lambda: SimpleNamespace(classify=lambda f, c: Verdict(
        category=Category.UNKNOWN, confidence=0.1, evidence=[f"seen {EMAIL}"], suggested_action=f"ping {IP}", source="llm")))
    report = render(result, "test")
    assert EMAIL not in report and IP not in report and "abcd1234efgh5678" not in report
    assert "Privacy:" in report and "email x" in report


def test_no_provider_needed_when_rules_suffice():
    f = TestFailure(name="t", rerun_recorded=True, rerun_passed=True)
    def boom():
        raise AssertionError("provider must not be created")
    triage(RunInput(failures=[f], total_tests=1), boom)
