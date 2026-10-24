import io
import json
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import pr_security_auditor as auditor


class FakeResponse:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.value).encode()


class DiffScanningTests(unittest.TestCase):
    def test_only_added_lines_are_scanned_with_new_line_numbers(self):
        diff = """\
diff --git a/sample.py b/sample.py
--- a/sample.py
+++ b/sample.py
@@ -1,2 +1,3 @@
 safe = True
-eval(old_value)
+eval(user_input)
+password = "super-secret-value-123"
"""
        lines = auditor.parse_added_lines(diff)

        self.assertEqual([(item.path, item.line) for item in lines], [("sample.py", 2), ("sample.py", 3)])
        findings = auditor.scan_added_lines(lines)
        self.assertEqual([finding.category for finding in findings], ["Dynamic evaluation", "Secret"])

    def test_secret_value_does_not_appear_in_findings_or_report(self):
        secret = "password = 'super-secret-value-123'"
        findings = auditor.scan_added_lines([auditor.AddedLine("config.py", 4, secret)])

        self.assertEqual(len(findings), 1)
        self.assertNotIn("super-secret-value-123", findings[0].message)
        self.assertNotIn("super-secret-value-123", auditor.render_report(findings, []))

    def test_masks_common_personal_information(self):
        text = (
            '{"name": "Avery Example", "email": "avery@example.com", '
            '"phone": "4155552671", "address": "123 Main Street, Apt 4"}'
        )

        masked = auditor._redact_personal_info(text)

        for personal_value in (
            "Avery Example",
            "avery@example.com",
            "4155552671",
            "123 Main Street, Apt 4",
        ):
            self.assertNotIn(personal_value, masked)
        self.assertIn("[REDACTED_PERSON]", masked)
        self.assertIn("[REDACTED_EMAIL]", masked)
        self.assertIn("[REDACTED_PHONE]", masked)
        self.assertIn("[REDACTED_ADDRESS]", masked)
        self.assertEqual(
            auditor._redact_personal_info("Contact Avery Example for details."),
            "Contact [REDACTED_PERSON] for details.",
        )

    def test_detects_interpolated_sql_and_unsafe_deserialization(self):
        lines = [
            auditor.AddedLine("db.py", 1, 'cursor.execute(f"SELECT * FROM users WHERE id={user_id}")'),
            auditor.AddedLine("cache.py", 2, "pickle.loads(payload)"),
        ]

        findings = auditor.scan_added_lines(lines)

        self.assertEqual({finding.category for finding in findings}, {"Interpolated SQL", "Unsafe deserialization"})

    def test_diff_paths_with_spaces_are_supported(self):
        diff = """\
diff --git "a/folder name/file.py" "b/folder name/file.py"
--- "a/folder name/file.py"
+++ "b/folder name/file.py"
@@ -0,0 +1 @@
+eval(source)
"""

        lines = auditor.parse_added_lines(diff)

        self.assertEqual(lines[0].path, "folder name/file.py")

    def test_placeholder_credentials_are_not_reported(self):
        findings = auditor.scan_added_lines(
            [auditor.AddedLine("config.py", 1, 'api_key = "your_api_key_here"')]
        )

        self.assertEqual(findings, [])


class DependencyTests(unittest.TestCase):
    def test_requirements_parser_queries_only_exact_versions(self):
        dependencies, skipped = auditor.parse_requirements(
            "requests==2.31.0\nflask>=2.0\n# comment\n", "requirements.txt"
        )

        self.assertEqual([(item.name, item.version) for item in dependencies], [("requests", "2.31.0")])
        self.assertEqual(len(skipped), 1)

    def test_package_json_parser_reads_supported_dependency_sections(self):
        content = json.dumps(
            {
                "dependencies": {"safe-lib": "1.2.3", "range-lib": "^2.0.0"},
                "devDependencies": {"test-lib": "4.5.6"},
            }
        )

        dependencies, skipped = auditor.parse_package_json(content, "package.json")

        self.assertEqual({item.name for item in dependencies}, {"safe-lib", "test-lib"})
        self.assertEqual(len(skipped), 1)

    def test_osv_findings_include_advisory_and_severity(self):
        dependencies = [auditor.Dependency("PyPI", "example", "1.0.0", "requirements.txt")]
        response = {
            "results": [
                {
                    "vulns": [
                        {
                            "id": "GHSA-0000-0000-0000",
                            "summary": "Example issue",
                            "database_specific": {"severity": "HIGH"},
                        }
                    ]
                }
            ]
        }

        findings, errors = auditor.query_osv(
            dependencies,
            opener=lambda *_args, **_kwargs: FakeResponse(response),
        )

        self.assertEqual(errors, [])
        self.assertEqual(findings[0].severity, "HIGH")
        self.assertIn("GHSA-0000-0000-0000", findings[0].message)

    def test_report_escapes_untrusted_markdown(self):
        findings = [
            auditor.Finding(
                "HIGH",
                "Vulnerable | dependency",
                "file`name.md",
                1,
                "Advisory | <script>alert(1)</script>",
            )
        ]

        report = auditor.render_report(findings, [])

        self.assertIn(r"Vulnerable \| dependency", report)
        self.assertIn(r"file\`name\.md", report)
        self.assertNotIn("| <script>", report)

    def test_osv_network_error_is_reported(self):
        dependencies = [auditor.Dependency("npm", "example", "1.0.0", "package.json")]

        def fail(*_args, **_kwargs):
            raise OSError("network unavailable")

        findings, errors = auditor.query_osv(dependencies, opener=fail)

        self.assertEqual(findings, [])
        self.assertIn("network unavailable", errors[0])

    def test_malformed_osv_result_is_reported(self):
        dependencies = [auditor.Dependency("npm", "example", "1.0.0", "package.json")]

        findings, errors = auditor.query_osv(
            dependencies,
            opener=lambda *_args, **_kwargs: FakeResponse({"results": [None]}),
        )

        self.assertEqual(findings, [])
        self.assertIn("invalid result", errors[0])


class GeminiTests(unittest.TestCase):
    def test_default_model_is_gemini_flash(self):
        self.assertEqual(auditor.DEFAULT_GEMINI_MODEL, "gemini-3.8-flash")

    def _response(self, findings, citations=True):
        text_block = {"type": "text", "text": json.dumps({"findings": findings})}
        if citations:
            text_block["annotations"] = [
                {
                    "type": "url_citation",
                    "url": "https://osv.dev/",
                    "title": "OSV",
                }
            ]
        return {
            "status": "completed",
            "steps": [{"type": "model_output", "content": [text_block]}],
        }

    def test_request_excludes_secrets_and_uses_google_search(self):
        lines = [
            auditor.AddedLine("config.py", 1, 'api_key = "example-secret-value-12345"'),
            auditor.AddedLine("app.py", 2, "user_input = request.args.get('q')"),
        ]
        captured = {}

        def fake_open(request, **_kwargs):
            captured["body"] = json.loads(request.data)
            captured["url"] = request.full_url
            captured["api_key_header"] = request.get_header("X-goog-api-key")
            captured["authorization"] = request.get_header("Authorization")
            return FakeResponse(self._response([
                {
                    "severity": "MEDIUM",
                    "category": "Input handling",
                    "path": "changed-file-1",
                    "line": 2,
                    "message": "Validate input before using it.",
                    "fixes": ["Validate against the expected schema."],
                    "references": [],
                }
            ]))

        findings, notes = auditor.query_gemini(
            lines, [], [], "test-key", opener=fake_open
        )

        request_text = json.dumps(captured["body"])
        self.assertEqual(captured["url"], auditor.GEMINI_INTERACTIONS_URL)
        self.assertTrue(captured["api_key_header"])
        self.assertIsNone(captured["authorization"])
        self.assertEqual(captured["body"]["model"], "gemini-3.8-flash")
        self.assertFalse(captured["body"]["store"])
        self.assertEqual(captured["body"]["tools"][0], {"type": "google_search"})
        self.assertIn("current public vulnerability", captured["body"]["input"])
        self.assertNotIn("example-secret-value-12345", request_text)
        self.assertNotIn("config.py", request_text)
        self.assertEqual(findings[0].path, "app.py")
        self.assertEqual(findings[0].category, "LLM: Input handling")
        self.assertEqual(findings[0].remediation, "1. Validate against the expected schema.")
        self.assertEqual(notes, ["1 added lines were excluded from LLM review."])

    def test_personal_information_is_masked_before_gemini_request(self):
        personal_line = (
            '{"name": "Avery Example", "email": "avery@example.com", '
            '"phone": "+1 (415) 555-2671", "address": "123 Main Street, Apt 4"}'
        )
        captured = {}

        def fake_open(request, **_kwargs):
            captured["body"] = json.loads(request.data)
            return FakeResponse(self._response([
                {
                    "severity": "LOW",
                    "category": "Privacy",
                    "path": "changed-file-1",
                    "line": 7,
                    "message": "Contact Avery Example at avery@example.com",
                    "fixes": ["Call +1 (415) 555-2671 at 123 Main Street"],
                    "references": [],
                }
            ]))

        findings, notes = auditor.query_gemini(
            [auditor.AddedLine("Avery Example/profile.py", 7, personal_line)],
            [
                auditor.Finding(
                    "LOW",
                    "Review",
                    "Avery Example/profile.py",
                    7,
                    "Contact Avery Example at avery@example.com",
                    "Call +1 (415) 555-2671 at 123 Main Street",
                )
            ],
            [auditor.Dependency("npm", "safe-package", "1.2.3", "profile.py")],
            "test-key",
            opener=fake_open,
        )

        payload_text = json.dumps(captured["body"])
        for personal_value in (
            "Avery Example",
            "avery@example.com",
            "+1 (415) 555-2671",
            "123 Main Street",
            "profile.py",
        ):
            self.assertNotIn(personal_value, payload_text)
        self.assertIn("changed-file-1", payload_text)
        self.assertIn("[REDACTED_PERSON]", payload_text)
        self.assertIn("[REDACTED_EMAIL]", payload_text)
        self.assertIn("[REDACTED_PHONE]", payload_text)
        self.assertIn("[REDACTED_ADDRESS]", payload_text)
        self.assertIn("Personal information was masked in 1 added lines", notes[0])
        result_text = json.dumps(
            {"message": findings[0].message, "fix": findings[0].remediation}
        )
        self.assertNotIn("Avery Example", result_text)
        self.assertNotIn("avery@example.com", result_text)
        self.assertNotIn("+1 (415) 555-2671", result_text)
        self.assertNotIn("123 Main Street", result_text)

    def test_findings_must_match_submitted_location(self):
        response = self._response([
            {
                "severity": "HIGH",
                "category": "Issue",
                "path": "changed-file-2",
                "line": 42,
                "message": "Unverified finding.",
                "fixes": ["Fix it."],
                "references": [],
            }
        ])
        findings, _notes = auditor.query_gemini(
            [auditor.AddedLine("app.py", 2, "value = user_input")],
            [], [], "test-key",
            opener=lambda *_args, **_kwargs: FakeResponse(response),
        )
        self.assertEqual(findings, [])

    def test_report_discloses_gemini_model_review(self):
        report = auditor.render_report(
            [auditor.Finding(
                "HIGH", "Vulnerability", "app.py", 2, "Recent issue",
                "Upgrade the affected dependency.",
                ("https://osv.dev/advisory/example",),
            )],
            [],
            external_review="gemini-3.8-flash",
        )
        self.assertIn("Google Gemini model", report)
        self.assertIn(r"gemini-3\.8-flash", report)
        self.assertIn(r"Upgrade the affected dependency\.", report)
        self.assertIn(r"https://osv\.dev/advisory/example", report)

    def test_recent_vulnerability_requires_verified_grounding_source(self):
        response = self._response([
            {
                "severity": "HIGH",
                "category": "Vulnerability",
                "path": "changed-file-1",
                "line": 2,
                "message": "A recent issue affects this code.",
                "fixes": ["Upgrade to a patched version."],
                "references": ["https://osv.dev/"],
            }
        ])
        findings, notes = auditor.query_gemini(
            [auditor.AddedLine("app.py", 2, "value = user_input")],
            [], [], "test-key",
            opener=lambda *_args, **_kwargs: FakeResponse(response),
        )
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].references, ("https://osv.dev/",))
        self.assertEqual(findings[0].remediation, "1. Upgrade to a patched version.")
        self.assertFalse(any(note.startswith("ERROR:") for note in notes))

    def test_missing_google_search_grounding_marks_llm_check_incomplete(self):
        response = self._response([], citations=False)
        _findings, notes = auditor.query_gemini(
            [auditor.AddedLine("app.py", 2, "value = user_input")],
            [], [], "test-key",
            opener=lambda *_args, **_kwargs: FakeResponse(response),
        )
        self.assertTrue(any(note.startswith("ERROR:") and "citations" in note for note in notes))

    def test_invalid_model_path_is_rejected_before_request(self):
        with patch.object(auditor.urllib.request, "urlopen") as urlopen:
            _findings, notes = auditor.query_gemini(
                [], [], [], "test-key", model="../model"
            )
        urlopen.assert_not_called()
        self.assertIn("Invalid Gemini model name.", notes)

    def test_http_error_includes_google_error_message(self):
        error_body = json.dumps(
            {"error": {"message": "Model name not found for API version v1beta."}}
        ).encode()

        def fail_request(*_args, **_kwargs):
            raise urllib.error.HTTPError(
                "https://generativelanguage.googleapis.com",
                404,
                "Not Found",
                {},
                io.BytesIO(error_body),
            )

        _findings, notes = auditor.query_gemini(
            [], [], [], "test-key", opener=fail_request
        )

        self.assertIn("404", notes[0])
        self.assertIn("Model name not found", notes[0])


class ManifestPathTests(unittest.TestCase):
    def test_manifest_paths_cannot_escape_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dependencies, messages = auditor.load_changed_dependencies(root, ["../requirements.txt"])

        self.assertEqual(dependencies, [])
        self.assertIn("outside repository root", messages[0])

    def test_staged_manifest_is_read_from_git_index(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "requirements.txt").write_text("requests==2.0.0\n", encoding="utf-8")
            with patch.object(auditor, "_git", return_value="requests==1.0.0\n") as git_call:
                dependencies, messages = auditor.load_changed_dependencies(
                    root, ["requirements.txt"], staged=True
                )

        git_call.assert_called_once_with(root, ["show", ":requirements.txt"])
        self.assertEqual(messages, [])
        self.assertEqual(dependencies[0].version, "1.0.0")

    def test_missing_gemini_key_marks_mandatory_check_incomplete(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(auditor, "_get_repo_root", return_value=root), patch.object(
                auditor, "_git", side_effect=["", b""]
            ), patch.object(auditor, "query_gemini") as query:
                _findings, errors = auditor.collect_audit(root, gemini_api_key=None)

        query.assert_not_called()
        self.assertTrue(any("Required Gemini review" in error for error in errors))



if __name__ == "__main__":
    unittest.main()
