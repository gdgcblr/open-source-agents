import json

import pytest

from analyzer import analyze_files
from diff_parser import parse_unified_diff
from main import load_config


def test_safe_diff_has_no_findings():
    diff = """\
diff --git a/calculator.py b/calculator.py
--- a/calculator.py
+++ b/calculator.py
@@ -1,2 +1,3 @@
 def add(a, b):
     return a + b
+
"""
    files = parse_unified_diff(diff)
    report = analyze_files(files)

    assert report.files_changed == 1
    assert report.additions == 1
    assert report.deletions == 0
    assert report.findings == []


def test_report_json_shape():
    files = parse_unified_diff("""\
diff --git a/requirements.txt b/requirements.txt
--- a/requirements.txt
+++ b/requirements.txt
@@ -1 +1,2 @@
 pytest
+requests
""")

    data = analyze_files(files).to_dict()

    assert "summary" in data
    assert "findings" in data
    assert data["summary"]["files_changed"] == 1
    assert data["findings"][0]["rule_id"] == "DEP001"
    assert json.loads(json.dumps(data))["findings"]


def test_disabled_rule_does_not_run():
    files = parse_unified_diff("""\
diff --git a/requirements.txt b/requirements.txt
--- a/requirements.txt
+++ b/requirements.txt
@@ -1 +1,2 @@
 pytest
+requests
""")

    report = analyze_files(
        files,
        {
            "rules": {
                "secret_detection": False,
                "sensitive_paths": False,
                "infrastructure_changes": False,
                "dependency_changes": False,
                "test_changes": False,
                "change_size": False,
            },
            "thresholds": {},
            "sensitive_paths": [],
        },
    )

    assert report.findings == []


def test_invalid_json_config_raises_error(tmp_path):
    config_path = tmp_path / "invalid.json"
    config_path.write_text("{invalid", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid JSON config"):
        load_config(str(config_path))


def test_non_object_config_raises_error(tmp_path):
    config_path = tmp_path / "invalid.json"
    config_path.write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="JSON object"):
        load_config(str(config_path))


def test_negative_threshold_is_rejected(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"thresholds": {"max_added_lines": -1}}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="non-negative integer"):
        load_config(str(config_path))