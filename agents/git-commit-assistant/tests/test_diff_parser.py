"""Tests for the unified-diff parser (no git, no network)."""

from commit_assistant.diff_parser import (
    ADDED,
    DELETED,
    MODIFIED,
    RENAMED,
    parse_diff,
)


def test_empty_diff_is_empty():
    summary = parse_diff("")
    assert summary.is_empty()
    assert summary.file_count == 0
    assert summary.total_added == 0
    assert summary.total_removed == 0


def test_added_file(read_fixture):
    summary = parse_diff(read_fixture("add_module.diff"))
    assert summary.file_count == 1
    fc = summary.files[0]
    assert fc.path == "commit_assistant/greet.py"
    assert fc.change_type == ADDED
    assert fc.ext == ".py"
    assert fc.added == 6
    assert fc.removed == 0


def test_deleted_file(read_fixture):
    summary = parse_diff(read_fixture("delete_file.diff"))
    assert summary.file_count == 1
    fc = summary.files[0]
    assert fc.path == "src/legacy/helper.py"
    assert fc.change_type == DELETED
    assert fc.removed == 4
    assert fc.added == 0


def test_modified_file(read_fixture):
    summary = parse_diff(read_fixture("fix_bug.diff"))
    assert summary.file_count == 1
    fc = summary.files[0]
    assert fc.path == "src/bugfix/handler.py"
    assert fc.change_type == MODIFIED
    assert fc.added == 3
    assert fc.removed == 1


def test_docs_file(read_fixture):
    summary = parse_diff(read_fixture("docs_only.diff"))
    assert summary.file_count == 1
    assert summary.files[0].ext == ".md"


def test_header_lines_not_counted(read_fixture):
    # The +++/--- header lines must never inflate the +/- counts.
    summary = parse_diff(read_fixture("add_module.diff"))
    assert summary.total_added == 6  # not 7 despite the "+++ b/..." line


def test_rename_detected():
    diff = (
        "diff --git a/old/name.py b/new/name.py\n"
        "similarity index 100%\n"
        "rename from old/name.py\n"
        "rename to new/name.py\n"
    )
    summary = parse_diff(diff)
    assert summary.file_count == 1
    fc = summary.files[0]
    assert fc.change_type == RENAMED
    assert fc.path == "new/name.py"


def test_multiple_files():
    diff = (
        "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-x\n+y\n"
        "diff --git a/b.py b/b.py\nnew file mode 100644\n--- /dev/null\n+++ b/b.py\n@@ -0,0 +1 @@\n+z\n"
    )
    summary = parse_diff(diff)
    assert summary.file_count == 2
    assert summary.files[0].change_type == MODIFIED
    assert summary.files[1].change_type == ADDED
    assert summary.total_added == 2
    assert summary.total_removed == 1
