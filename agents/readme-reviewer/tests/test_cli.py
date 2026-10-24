import asyncio
import io
import json
import logging
from types import SimpleNamespace

import pytest

from review_core import cli
from review_core.analysis.scoring import CriterionScores, Failure, ReviewReport


def report(verdict="needs_changes", failures=(), fixes=("Do the thing",), score=84):
    return ReviewReport(
        overall_score=score,
        criterion_scores=CriterionScores(reproducibility=67, security=100),
        failures=list(failures),
        suggested_fixes=list(fixes),
        verdict=verdict,
    )


FAILURE = Failure(criterion="reproducibility", id="manifest_present", reason="No dependency manifest.")


class TTY(io.StringIO):
    def isatty(self):
        return True


# ---- progress and status line ---------------------------------------------- #
def test_progress_labels_follow_the_pipeline():
    p = cli.Progress()
    assert p.label() == "Reviewing: 0/4 reviewers done"
    p.update("security_reviewer", is_final=False)  # still working: not counted
    assert p.label() == "Reviewing: 0/4 reviewers done"
    p.update("security_reviewer", is_final=True)
    p.update("scope_reviewer", is_final=True)
    p.update("scope_reviewer", is_final=True)  # duplicate event is harmless
    assert p.label() == "Reviewing: 2/4 reviewers done"
    p.update("documentation_reviewer", True)
    p.update("reproducibility_reviewer", True)
    assert p.label() == "Merging the findings"
    p.update("review_aggregator", True)
    assert p.label() == "Scoring the report"


def test_unknown_authors_are_ignored():
    p = cli.Progress()
    p.update("review_reset", True)
    p.update("something_else", True)
    assert p.label() == "Reviewing: 0/4 reviewers done"


def test_status_line_plain_and_colored():
    assert cli.format_status("⠋", "Working", 12.7) == "⠋ Working (12s)"
    colored = cli.format_status("⠋", "Working", 3, color=True)
    assert "\033[" in colored and "Working" in colored and "(3s)" in colored


# ---- spinner ---------------------------------------------------------------- #
def test_spinner_off_a_terminal_prints_each_status_once():
    out = io.StringIO()
    p = cli.Progress()
    with cli.Spinner(p.label, stream=out) as spinner:
        spinner.tick()
        spinner.tick()  # unchanged: no repeat
        p.update("security_reviewer", True)
        spinner.tick()
    assert out.getvalue() == "- Reviewing: 0/4 reviewers done\n- Reviewing: 1/4 reviewers done\n"


def test_spinner_on_a_terminal_animates_and_clears_its_line():
    out = TTY()
    with cli.Spinner(lambda: "Working", stream=out):
        import time

        time.sleep(0.25)
    text = out.getvalue()
    assert "Working" in text and any(frame in text for frame in cli.FRAMES)
    assert text.endswith("\r\033[K")  # the status line is erased when done


def test_no_color_env_disables_color(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    assert cli.use_color(TTY()) and not cli.use_color(io.StringIO())
    monkeypatch.setenv("NO_COLOR", "1")
    assert not cli.use_color(TTY())


# ---- report formatting ------------------------------------------------------ #
def test_report_shows_score_failures_and_fixes():
    text = cli.format_report(report(failures=[FAILURE]))
    assert "Score 84/100" in text and "needs_changes" in text
    assert "reproducibility 67" in text and "security 100" in text
    assert "manifest_present" in text and "No dependency manifest." in text
    assert "1. Do the thing" in text and "\033[" not in text


def test_ready_report_without_failures_says_so():
    text = cli.format_report(report("ready", fixes=(), score=100))
    assert "ready" in text and "All checks passed." in text and "Failures" not in text


def test_report_color_adds_escape_codes():
    assert "\033[" in cli.format_report(report(failures=[FAILURE]), color=True)


# ---- friendly errors -------------------------------------------------------- #
@pytest.mark.parametrize("exc,expected", [
    (RuntimeError("429 RESOURCE_EXHAUSTED quota"), "rate limiting"),
    (RuntimeError("503 UNAVAILABLE high demand"), "temporarily unavailable"),
    (RuntimeError("401 invalid api key"), "API key"),
    (ValueError("MODEL_PROVIDER=nvidia requires MODEL_NAME"), "requires MODEL_NAME"),
    (RuntimeError("boom"), "--debug"),
])
def test_friendly_error_messages(exc, expected):
    assert expected in cli.friendly_error(exc)


# ---- run_review with a fake runner ------------------------------------------ #
class FakeEvent:
    def __init__(self, author, text=None, final=True):
        self.author, self._final = author, final
        self.content = SimpleNamespace(parts=[SimpleNamespace(text=text)]) if text else None

    def is_final_response(self):
        return self._final


class FakeRunner:
    def __init__(self, events):
        self.events = events
        self.sessions = []
        self.session_service = SimpleNamespace(create_session=self._create)

    async def _create(self, app_name, user_id):
        self.sessions.append(user_id)
        return SimpleNamespace(id=f"s{len(self.sessions)}")

    async def run_async(self, user_id, session_id, new_message):
        for event in self.events:
            yield event


def test_run_review_returns_only_the_finalizer_message_and_tracks_progress():
    events = [
        FakeEvent("review_reset"),
        FakeEvent("security_reviewer", "Let's first call review_security (model thinking)"),
        FakeEvent("review_aggregator", "{aggregator json}"),
        FakeEvent("report_finalizer", '{"final": true}'),
    ]
    progress = cli.Progress()
    result = asyncio.run(cli.run_review("Review x", progress, runner_factory=lambda: FakeRunner(events)))
    assert result == '{"final": true}'
    assert "security" in progress.done and progress.scoring


def test_run_review_without_a_finalizer_message_returns_none():
    result = asyncio.run(cli.run_review("Review x", cli.Progress(), runner_factory=lambda: FakeRunner([FakeEvent("scope_reviewer", "x")])))
    assert result is None


# ---- review_once / main ------------------------------------------------------ #
def patch_run(monkeypatch, result=None, error=None):
    async def fake(text, progress, spinner=None, runner_factory=None):
        if error:
            raise error
        return result

    monkeypatch.setattr(cli, "run_review", fake)


def test_ready_report_exits_zero_and_prints_only_the_report(monkeypatch, capsys):
    patch_run(monkeypatch, report("ready", fixes=(), score=100).model_dump_json())
    assert cli.review_once("Review x", as_json=False, debug=False) == 0
    out = capsys.readouterr().out
    assert "Score 100/100" in out and "thinking" not in out


def test_needs_changes_exits_one(monkeypatch, capsys):
    patch_run(monkeypatch, report(failures=[FAILURE]).model_dump_json())
    assert cli.review_once("Review x", as_json=False, debug=False) == 1
    assert "manifest_present" in capsys.readouterr().out


def test_json_flag_prints_raw_json(monkeypatch, capsys):
    raw = report("ready", fixes=(), score=100).model_dump_json()
    patch_run(monkeypatch, raw)
    cli.review_once("Review x", as_json=True, debug=False)
    assert json.loads(capsys.readouterr().out)["overall_score"] == 100


def test_provider_error_is_friendly_not_a_traceback(monkeypatch, capsys):
    patch_run(monkeypatch, error=RuntimeError("429 RESOURCE_EXHAUSTED"))
    assert cli.review_once("Review x", as_json=False, debug=False) == 1
    err = capsys.readouterr().err
    assert "rate limiting" in err and "Traceback" not in err


def test_debug_reraises(monkeypatch):
    patch_run(monkeypatch, error=RuntimeError("boom"))
    with pytest.raises(RuntimeError):
        cli.review_once("Review x", as_json=False, debug=True)


def test_missing_or_invalid_report_is_an_error(monkeypatch, capsys):
    patch_run(monkeypatch, None)
    assert cli.review_once("Review x", as_json=False, debug=False) == 1
    patch_run(monkeypatch, "Path not found: x. Did you mean 'agents/y'?")
    assert cli.review_once("Review x", as_json=False, debug=False) == 1
    captured = capsys.readouterr()
    assert "error: Path not found: x. Did you mean 'agents/y'?" in captured.err and captured.out == ""


def test_main_with_a_folder_sends_a_review_request(monkeypatch):
    seen = []
    monkeypatch.setattr(cli, "setup", lambda debug: None)
    monkeypatch.setattr(cli, "review_once", lambda text, as_json, debug: seen.append(text) or 0)
    assert cli.main(["template"]) == 0
    assert seen == ["Review template"]


def test_interactive_mode_loops_until_exit(monkeypatch):
    seen = []
    answers = iter(["template", "", "Review agents/foo", "exit"])
    monkeypatch.setattr(cli, "setup", lambda debug: None)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    monkeypatch.setattr(cli, "review_once", lambda text, as_json, debug: seen.append(text) or 0)
    assert cli.main([]) == 0
    assert seen == ["Review template", "Review agents/foo"]


def test_interactive_mode_ends_cleanly_on_ctrl_d(monkeypatch):
    def eof(prompt=""):
        raise EOFError

    monkeypatch.setattr(cli, "setup", lambda debug: None)
    monkeypatch.setattr("builtins.input", eof)
    assert cli.main([]) == 0


# ---- litellm log noise ------------------------------------------------------ #
def test_nvidia_model_silences_litellm_info_logs(monkeypatch):
    pytest.importorskip("litellm")
    from review_core.models import get_model

    monkeypatch.setenv("MODEL_PROVIDER", "nvidia")
    monkeypatch.setenv("MODEL_NAME", "some/model")
    monkeypatch.setenv("NVIDIA_API_KEY", "test-not-a-real-key")
    for name in ("LiteLLM", "LiteLLM Router", "LiteLLM Proxy"):
        logging.getLogger(name).setLevel(logging.INFO)
    get_model()
    for name in ("LiteLLM", "LiteLLM Router", "LiteLLM Proxy"):
        assert logging.getLogger(name).level >= logging.WARNING
