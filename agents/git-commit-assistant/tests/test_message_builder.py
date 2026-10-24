"""Tests for the deterministic mock heuristic."""

from commit_assistant.diff_parser import (
    ADDED,
    DELETED,
    MODIFIED,
    DiffSummary,
    FileChange,
    parse_diff,
)
from commit_assistant.message_builder import build_message, render


def _summary(*files):
    return DiffSummary(files=list(files))


def test_added_source_is_feat(read_fixture):
    summary = parse_diff(read_fixture("add_module.diff"))
    msg = build_message(summary)
    assert msg.type == "feat"
    assert msg.scope == "commit_assistant"
    assert "greet" in msg.subject


def test_docs_only_is_docs(read_fixture):
    summary = parse_diff(read_fixture("docs_only.diff"))
    msg = build_message(summary)
    assert msg.type == "docs"


def test_delete_only_is_refactor(read_fixture):
    summary = parse_diff(read_fixture("delete_file.diff"))
    msg = build_message(summary)
    assert msg.type == "refactor"


def test_bug_path_is_fix(read_fixture):
    summary = parse_diff(read_fixture("fix_bug.diff"))
    msg = build_message(summary)
    assert msg.type == "fix"


def test_all_tests_is_test():
    summary = _summary(
        FileChange("tests/test_x.py", MODIFIED, added=5),
        FileChange("tests/test_y.py", ADDED, added=3),
    )
    assert build_message(summary).type == "test"


def test_manifest_only_is_chore():
    summary = _summary(FileChange("requirements.txt", MODIFIED, added=1))
    assert build_message(summary).type == "chore"


def test_no_body_suppresses_bullets(read_fixture):
    summary = parse_diff(read_fixture("add_module.diff"))
    msg = build_message(summary, no_body=True)
    assert msg.body_bullets == []
    assert "\n" not in render(msg)


def test_bullet_cap_over_ten():
    files = [FileChange(f"pkg/file_{i}.py", MODIFIED, added=1) for i in range(13)]
    msg = build_message(_summary(*files))
    # 10 file bullets + 1 "and N more" summary line.
    assert len(msg.body_bullets) == 11
    assert msg.body_bullets[-1].startswith("…and 3 more")


def test_scope_single_root_file():
    summary = _summary(FileChange("setup.py", MODIFIED, added=20))
    msg = build_message(summary)
    # setup.py is a manifest -> chore, single root file -> stem scope.
    assert msg.scope == "setup"


def test_render_header_with_scope():
    summary = _summary(FileChange("pkg/mod.py", ADDED, added=5))
    text = render(build_message(summary, no_body=True))
    assert text.startswith("feat(pkg): ")


def test_render_header_without_scope():
    summary = _summary(
        FileChange("a/x.py", MODIFIED, added=1),
        FileChange("b/y.py", MODIFIED, added=1),
    )
    text = render(build_message(summary, no_body=True))
    assert ": " in text and "(" not in text.split(":")[0]


def test_subject_soft_capped():
    files = [FileChange(f"dir/really_long_name_{i}.py", MODIFIED, added=1) for i in range(40)]
    msg = build_message(_summary(*files))
    assert len(msg.subject) <= 72
