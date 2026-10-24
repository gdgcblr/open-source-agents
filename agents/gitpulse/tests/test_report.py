import json

import pytest

from agents.gitpulse.core import (
    GitPulseError,
    LintFinding,
    ModelResponseError,
    SecurityFinding,
    format_conventional_commit,
    lint_conventional_commit,
    parse_model_review,
    render_report,
    write_report,
)


def test_format_conventional_commit_normalizes_scope() -> None:
    assert format_conventional_commit("FEAT", " GitPulse ", "add review mode") == (
        "feat(gitpulse): add review mode"
    )


def test_commit_message_linter_accepts_valid_and_breaking_headers() -> None:
    assert lint_conventional_commit("feat(gitpulse): add static linting") == []
    assert lint_conventional_commit("fix!: reject malformed review output") == []


def test_commit_message_linter_reports_invalid_header_and_type() -> None:
    assert lint_conventional_commit("not a conventional header")
    assert "Unsupported type 'feature'" in lint_conventional_commit("feature: add a feature")[0]


def test_parse_model_review_validates_fields() -> None:
    response = json.dumps(
        {
            "change_type": "feat",
            "scope": "gitpulse",
            "summary": "review local branch changes",
            "change_summary": ["Adds a local diff review workflow."],
            "recommendations": ["Run the focused unit tests."],
        }
    )

    review = parse_model_review(response)

    assert review.change_type == "feat"
    assert review.scope == "gitpulse"
    assert review.change_summary == ("Adds a local diff review workflow.",)


def test_parse_model_review_accepts_json_fence_and_rejects_invalid_data() -> None:
    valid_payload = {
        "change_type": "feat",
        "scope": None,
        "summary": "add helper",
        "change_summary": [],
        "recommendations": [],
    }
    wrapped_json = f"```json\n{json.dumps(valid_payload)}\n```"
    invalid_type = json.dumps({**valid_payload, "change_type": "attack"})

    assert parse_model_review(wrapped_json).change_type == "feat"
    with pytest.raises(ModelResponseError):
        parse_model_review(invalid_type)
    with pytest.raises(ModelResponseError, match="valid JSON"):
        parse_model_review("Here is the JSON: {}")


def test_parse_model_review_normalizes_scope_and_commit_prefixed_summary() -> None:
    response = json.dumps(
        {
            "change_type": "feat",
            "scope": "text_utils",
            "summary": "feat(text_utils): add normalize_project_name helper",
            "change_summary": ["Adds a project-name normalizer."],
            "recommendations": [],
        }
    )

    review = parse_model_review(response)

    assert review.scope == "text-utils"
    assert review.summary == "add normalize_project_name helper"
    assert format_conventional_commit(review.change_type, review.scope, review.summary) == (
        "feat(text-utils): add normalize_project_name helper"
    )


def test_report_keeps_scanner_findings_when_model_is_skipped() -> None:
    finding = SecurityFinding(
        category="hardcoded-credential",
        severity="medium",
        file_path="src/config.py",
        line_number=8,
        message="Possible hardcoded credential detected; value redacted.",
    )

    report = render_report("upstream/main", [finding], None, model_status="skipped")

    assert "AI analysis:** Skipped" in report
    assert "src/config.py:8" in report
    assert "value redacted" in report
    assert "not proof that the change is secure" not in report


def test_report_notes_no_findings_are_not_a_security_guarantee() -> None:
    report = render_report("upstream/main", [], None, model_status="skipped")

    assert "No findings were detected by the selected scanners. This is not proof" in report


def test_report_includes_ruff_findings_separately() -> None:
    finding = LintFinding(
        file_path="src/main.py",
        line_number=3,
        code="F401",
        message="Unused import",
    )

    report = render_report(
        "upstream/main",
        [],
        None,
        model_status="skipped",
        lint_findings=[finding],
        lint_status="completed",
    )

    assert "Python lint (Ruff):** Completed" in report
    assert "src/main.py:3" in report
    assert "F401" in report


def test_report_explains_gitleaks_failure_and_model_skip() -> None:
    report = render_report(
        "upstream/main...feature/topic",
        [],
        None,
        model_status="skipped",
        secret_scanner="both",
        secret_scan_status="failed",
        secret_scan_note="Gitleaks unavailable; heuristic results only.",
        model_note="AI review skipped because the dedicated scanner did not complete.",
    )

    assert "Secret scanner:** both (Failed)" in report
    assert "Gitleaks unavailable" in report
    assert "AI review skipped because the dedicated scanner did not complete" in report


def test_write_report_refuses_overwrite_by_default(tmp_path) -> None:
    destination = tmp_path / "review.md"
    destination.write_text("existing", encoding="utf-8")

    with pytest.raises(GitPulseError, match="already exists"):
        write_report("new", destination)
    write_report("new", destination, overwrite=True)
    assert destination.read_text(encoding="utf-8") == "new"