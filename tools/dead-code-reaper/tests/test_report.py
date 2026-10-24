from dead_code_reaper.report import build_patch


def test_patch_handles_edits_and_deletions():
    patch = build_patch({"a.py": "x = 1\ny = 2\n", "b.py": "z = 3\n"},
                        {"a.py": "x = 1\n", "b.py": None})
    assert "diff --git a/a.py b/a.py" in patch and "-y = 2" in patch
    assert "deleted file mode 100644" in patch and "+++ /dev/null" in patch


def test_patch_marks_missing_final_newline():
    patch = build_patch({"a.py": "x = 1\ny = 2"}, {"a.py": "x = 1\n"})
    assert "\\ No newline at end of file" in patch

