from diff_parser import parse_unified_diff


def test_parse_added_file_and_line_numbers():
    diff = """\
diff --git a/app.py b/app.py
new file mode 100644
--- /dev/null
+++ b/app.py
@@ -0,0 +1,2 @@
+first
+second
"""
    files = parse_unified_diff(diff)

    assert len(files) == 1
    assert files[0].status == "added"
    assert files[0].path == "app.py"
    assert [line.new_line_number for line in files[0].added_lines] == [1, 2]


def test_deleted_lines_are_not_additions():
    diff = """\
diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1,2 +1,1 @@
-old_value
 kept_value
"""
    files = parse_unified_diff(diff)

    assert len(files[0].deleted_lines) == 1
    assert len(files[0].added_lines) == 0


def test_rename_is_detected():
    diff = """\
diff --git a/old.py b/new.py
similarity index 100%
rename from old.py
rename to new.py
"""
    files = parse_unified_diff(diff)

    assert len(files) == 1
    assert files[0].status == "renamed"
    assert files[0].path == "new.py"


def test_binary_file_is_marked():
    diff = """\
diff --git a/image.png b/image.png
index 1111111..2222222 100644
Binary files a/image.png and b/image.png differ
"""
    files = parse_unified_diff(diff)

    assert len(files) == 1
    assert files[0].is_binary is True


def test_empty_diff():
    assert parse_unified_diff("") == []