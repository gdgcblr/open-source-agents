from pathlib import Path

import pytest

from pr_draft_agent.output import (
    MAX_OUTPUT_BYTES,
    VERIFICATION_NOTICE,
    OutputError,
    validate_and_render,
)
from pr_draft_agent.repository import RepositorySnapshot

SNAPSHOT = RepositorySnapshot(
    root=Path("/unused"),
    files=(),
    diff="",
    diff_sha256="0" * 64,
    template="## Summary\n\n## Testing\n",
    template_source=None,
)

DRAFT = """# Handle missing configuration clearly

## Summary

Return an actionable error when the configuration file is absent.

## Testing

- [x] Manual check completed
- [ ] Run the test suite
"""


def _draft_for_rendered_bytes(target: int, filler: str = "x") -> str:
    """Build a draft whose rendered bytes, without the CLI newline, equal target."""
    prefix = "# Title\n\n"
    fixed = len((prefix + "\n\n" + VERIFICATION_NOTICE).encode("utf-8"))
    remaining = target - fixed
    assert remaining > 0
    unit = len(filler.encode("utf-8"))
    body = filler * (remaining // unit) + "x" * (remaining % unit)
    return prefix + body


def test_verification_notice_is_the_application_owned_text() -> None:
    assert VERIFICATION_NOTICE == (
        "Verification: This agent inspected staged changes only. It did not execute tests "
        "or verify runtime behavior. Review the draft and complete the checklist before submitting."
    )


def test_valid_draft_renders_with_exact_notice_once() -> None:
    rendered = validate_and_render(DRAFT, SNAPSHOT)

    assert rendered.startswith("# Handle missing configuration clearly\n\n## Summary")
    assert rendered.endswith(VERIFICATION_NOTICE)
    assert rendered.count(VERIFICATION_NOTICE) == 1
    assert f"\n\n{VERIFICATION_NOTICE}" in rendered
    assert not rendered.endswith("\n")
    assert "- [ ] Manual check completed" in rendered


@pytest.mark.parametrize("text", ["", "   ", " \n\t\n \t"])
def test_empty_or_whitespace_response_rejected(text: str) -> None:
    with pytest.raises(OutputError) as error:
        validate_and_render(text, SNAPSHOT)
    assert error.value.code == "INVALID_DRAFT"


@pytest.mark.parametrize(
    "text",
    [
        "Body without a title.",
        "#Title\n\nBody.",
        "# \n\nBody.",
        "## Summary\n\nBody.",
    ],
)
def test_missing_or_empty_title_rejected(text: str) -> None:
    with pytest.raises(OutputError) as error:
        validate_and_render(text, SNAPSHOT)
    assert error.value.code == "INVALID_DRAFT"


@pytest.mark.parametrize("text", ["# Title\n", "# Title\n\n \n\t\n"])
def test_missing_body_rejected(text: str) -> None:
    with pytest.raises(OutputError) as error:
        validate_and_render(text, SNAPSHOT)
    assert error.value.code == "INVALID_DRAFT"


def test_leading_blank_lines_are_removed() -> None:
    rendered = validate_and_render("\n\n" + DRAFT, SNAPSHOT)
    assert rendered.startswith("# Handle missing configuration clearly")


def test_checked_markers_are_unchecked_at_list_starts_only() -> None:
    draft = (
        "# Title\n\n"
        "- [x] tested\n"
        "  * [X] nested\n"
        "1. [x] ordered\n"
        "2) [X] ordered parenthesis\n"
    )
    rendered = validate_and_render(draft, SNAPSHOT)

    assert "- [ ] tested" in rendered
    assert "  * [ ] nested" in rendered
    assert "1. [ ] ordered" in rendered
    assert "2) [ ] ordered parenthesis" in rendered
    assert "[x]" not in rendered
    assert "[X]" not in rendered


def test_fenced_code_and_inline_text_are_unchanged() -> None:
    draft = (
        "# Title\n\n"
        "Before.\n\n"
        "```text\n"
        "- [x] inside a backtick fence\n"
        "```\n\n"
        "~~~markdown\n"
        "* [X] inside a tilde fence\n"
        "~~~\n\n"
        "After `[x]` inline code and a sentence with [x] text.\n"
        "Final task:\n"
        "- [x] outside fences\n"
    )
    rendered = validate_and_render(draft, SNAPSHOT)

    assert "- [x] inside a backtick fence" in rendered
    assert "* [X] inside a tilde fence" in rendered
    assert "After `[x]` inline code and a sentence with [x] text." in rendered
    assert "- [ ] outside fences" in rendered


def test_quoted_checked_task_is_unchecked() -> None:
    rendered = validate_and_render("# Title\n\n> - [x] Verified", SNAPSHOT)
    assert "> - [ ] Verified" in rendered


def test_html_comment_cannot_hide_verification_notice() -> None:
    with pytest.raises(OutputError) as error:
        validate_and_render("# Title\n\n<!-- source comment", SNAPSHOT)
    assert error.value.code == "INVALID_DRAFT"


@pytest.mark.parametrize("control", ["\x1b", "\x00", "\x9b", "\x7f", "\x1f", "\r"])
def test_terminal_control_characters_rejected(control: str) -> None:
    with pytest.raises(OutputError) as error:
        validate_and_render(f"# Title\n\nBody{control} text.\n", SNAPSHOT)
    assert error.value.code == "INVALID_DRAFT"


def test_newline_and_tab_allowed() -> None:
    rendered = validate_and_render("# Title\n\n- item\n\tcontinued\n", SNAPSHOT)
    assert "\tcontinued" in rendered


def test_notice_in_model_draft_is_not_duplicated() -> None:
    rendered = validate_and_render(
        f"# Title\n\nBody.\n\n{VERIFICATION_NOTICE}\n", SNAPSHOT
    )
    assert rendered.count(VERIFICATION_NOTICE) == 1


def test_rendered_limit_includes_notice_and_final_newline() -> None:
    draft = _draft_for_rendered_bytes(MAX_OUTPUT_BYTES - 1)
    rendered = validate_and_render(draft, SNAPSHOT)

    assert len((rendered + "\n").encode("utf-8")) == MAX_OUTPUT_BYTES

    with pytest.raises(OutputError) as error:
        validate_and_render(_draft_for_rendered_bytes(MAX_OUTPUT_BYTES), SNAPSHOT)
    assert error.value.code == "OUTPUT_TOO_LARGE"


def test_rendered_limit_is_bytes_not_characters() -> None:
    draft = _draft_for_rendered_bytes(MAX_OUTPUT_BYTES - 1, filler="\U0001f600")
    rendered = validate_and_render(draft, SNAPSHOT)

    assert len(rendered) < MAX_OUTPUT_BYTES
    assert len((rendered + "\n").encode("utf-8")) == MAX_OUTPUT_BYTES

    with pytest.raises(OutputError) as error:
        validate_and_render(
            "# Title\n\n" + "\U0001f600" * 5_000, SNAPSHOT
        )
    assert error.value.code == "OUTPUT_TOO_LARGE"


def test_notice_in_inline_code_is_preserved() -> None:
    draft = f"# Title\n\nExample `{VERIFICATION_NOTICE}`\n"
    rendered = validate_and_render(draft, SNAPSHOT)
    assert f"`{VERIFICATION_NOTICE}`" in rendered


def test_verification_notice_inside_code_is_preserved() -> None:
    draft = f"# Title\n\nExample:\n\n```text\n{VERIFICATION_NOTICE}\n```\n"
    rendered = validate_and_render(draft, SNAPSHOT)
    assert f"```text\n{VERIFICATION_NOTICE}\n```" in rendered
    assert rendered.endswith(VERIFICATION_NOTICE)


def test_unclosed_fence_cannot_hide_verification_notice() -> None:
    with pytest.raises(OutputError) as error:
        validate_and_render("# Title\n\n```text\nexample\n", SNAPSHOT)
    assert error.value.code == "INVALID_DRAFT"


def test_invalid_backtick_fence_info_does_not_hide_tasks() -> None:
    rendered = validate_and_render("# Title\n\n```bad`info\n- [x] real task\n", SNAPSHOT)
    assert "- [ ] real task" in rendered


def test_notice_alone_is_not_a_description() -> None:
    with pytest.raises(OutputError) as error:
        validate_and_render(f"# Title\n\n{VERIFICATION_NOTICE}", SNAPSHOT)
    assert error.value.code == "INVALID_DRAFT"


def test_invalid_unicode_is_a_sanitized_output_error() -> None:
    with pytest.raises(OutputError) as error:
        validate_and_render("# Title\n\nBody \ud800", SNAPSHOT)
    assert error.value.code == "INVALID_DRAFT"
    assert "Body" not in error.value.message
