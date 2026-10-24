import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import pr_guardian


class PRGuardianTests(unittest.TestCase):
    def test_mock_flags_eval(self):
        diff = """diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1,0 +1,2 @@
+result = eval(user_input)
+print(result)
"""
        report = pr_guardian.mock_review(diff)
        self.assertTrue(any("eval" in finding["title"].lower() for finding in report["findings"]))
        self.assertEqual(report["findings"][0]["file"], "app.py")

    def test_mock_flags_todo(self):
        diff = """+++ b/main.py
@@ -1,0 +1,1 @@
+# TODO: validate this input
"""
        report = pr_guardian.mock_review(diff)
        self.assertTrue(any("TODO" in finding["title"] for finding in report["findings"]))

    def test_validate_report_normalizes_invalid_values(self):
        report = pr_guardian.validate_report({
            "summary": "Looks okay",
            "findings": [{
                "severity": "impossible",
                "title": "Issue",
                "line": -3,
                "description": "Evidence",
                "suggestion": "Fix it",
            }],
        })
        self.assertEqual(report["findings"][0]["severity"], "info")
        self.assertIsNone(report["findings"][0]["line"])
        self.assertEqual(report["findings"][0]["file"], "Unknown file")

    def test_cli_mock_writes_json_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            diff_file = Path(temp_dir) / "test.diff"
            output_file = Path(temp_dir) / "report.json"
            diff_file.write_text("+++ b/app.py\n@@ -0,0 +1,1 @@\n+eval(user_input)\n", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(PROJECT_ROOT / "pr_guardian.py"),
                 "--diff", str(diff_file), "--provider", "mock", "--output", str(output_file)],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            payload = json.loads(output_file.read_text(encoding="utf-8"))
            self.assertEqual(payload["provider"], "mock")
            self.assertIn("findings", payload)


    def test_added_lines_skip_deleted_lines(self):
        diff = """diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1,3 +1,3 @@
 context = True
-old_value = 1
+new_value = 2
 final_context = True
"""
        result = pr_guardian.get_added_lines(diff)
        self.assertEqual(result["app.py"], {2})

    def test_added_lines_across_multiple_hunks(self):
        diff = """diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1,2 +1,3 @@
 context = True
+first = 1
 more_context = True
@@ -10,2 +11,3 @@
 another_context = True
+second = 2
 last_context = True
"""
        result = pr_guardian.get_added_lines(diff)
        self.assertEqual(result["app.py"], {2, 12})


if __name__ == "__main__":
    unittest.main()
