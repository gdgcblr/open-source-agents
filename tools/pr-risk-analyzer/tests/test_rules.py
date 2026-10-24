from diff_parser import parse_unified_diff
from rules import (
    detect_change_size,
    detect_dependency_changes,
    detect_infrastructure_changes,
    detect_secrets,
    detect_sensitive_paths,
    detect_test_changes,
)


def parse(diff):
    return parse_unified_diff(diff)


def test_added_secret_like_value_is_flagged_and_redacted():
    files = parse("""\
diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1 +1,2 @@
 existing = True
+api_key = "synthetic_secret_value_987654321"
""")

    findings = detect_secrets(files)

    assert len(findings) == 1
    assert findings[0].rule_id == "SEC001"
    assert "synthetic_secret_value_987654321" not in (
        findings[0].evidence or ""
    )


def test_deleted_secret_is_not_flagged_as_new():
    files = parse("""\
diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1 +1 @@
-api_key = "synthetic_secret_value_987654321"
+api_key = get_from_secret_store()
""")

    assert detect_secrets(files) == []


def test_placeholder_is_ignored():
    files = parse("""\
diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1 +1 @@
-api_key = None
+api_key = "your_api_key"
""")

    assert detect_secrets(files) == []


def test_sensitive_path_change():
    files = parse("""\
diff --git a/src/auth/login.py b/src/auth/login.py
--- a/src/auth/login.py
+++ b/src/auth/login.py
@@ -1 +1 @@
-return False
+return validate_user()
""")

    findings = detect_sensitive_paths(files, ["auth"])

    assert len(findings) == 1
    assert findings[0].rule_id == "CODE001"


def test_infrastructure_change():
    files = parse("""\
diff --git a/Dockerfile b/Dockerfile
--- a/Dockerfile
+++ b/Dockerfile
@@ -1 +1,2 @@
 FROM python:3.12-slim
+USER root
""")

    assert detect_infrastructure_changes(files)


def test_dependency_manifest_change():
    files = parse("""\
diff --git a/requirements.txt b/requirements.txt
--- a/requirements.txt
+++ b/requirements.txt
@@ -1 +1,2 @@
 pytest
+requests
""")

    assert detect_dependency_changes(files)


def test_deleted_test_lines_are_flagged():
    files = parse("""\
diff --git a/tests/test_auth.py b/tests/test_auth.py
--- a/tests/test_auth.py
+++ b/tests/test_auth.py
@@ -1,2 +1 @@
 def test_auth():
-    assert True
""")

    findings = detect_test_changes(files)

    assert len(findings) == 1
    assert findings[0].rule_id == "TEST001"


def test_change_size_thresholds():
    files = parse("""\
diff --git a/a.py b/a.py
--- a/a.py
+++ b/a.py
@@ -1 +1,3 @@
-old
+new
+another
+third
""")

    findings = detect_change_size(
        files,
        max_changed_files=0,
        max_added_lines=2,
    )

    assert len(findings) == 1
    assert findings[0].rule_id == "SIZE002"