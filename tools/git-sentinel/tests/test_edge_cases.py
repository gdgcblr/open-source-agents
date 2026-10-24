import unittest
import os
import sys

# Add parent directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from main import (
    scan_diff_text,
    mask_secret,
    calculate_shannon_entropy,
    is_test_file_or_mock,
    is_python_test_ast,
    infer_env_var_name,
    should_skip_file,
    format_env_value,
    insert_python_import_os,
    try_decode_base64_secret,
    scan_multiline_block,
)


class TestGitSentinelEdgeCases(unittest.TestCase):

    def test_modern_openai_keys_detected(self):
        diff = (
            "+++ b/app/services/llm.py\n"
            "@@ -1,1 +1,2 @@\n"
            "+OPENAI_CLIENT_KEY = 'sk-proj-abc123XYZ456789-_ABCDEFGHIJKLMNOPQRSTUVWXYZ123456'\n"
        )
        findings = scan_diff_text(diff)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].pattern_name, "OpenAI API Key")

    def test_anthropic_claude_keys_detected_without_openai_collision(self):
        diff = (
            "+++ b/config.py\n"
            "@@ -1,1 +1,2 @@\n"
            "+CLAUDE_KEY = 'sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123456789-_abcdef'\n"
        )
        findings = scan_diff_text(diff)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].pattern_name, "Anthropic Claude API Key")

    def test_deleted_lines_not_flagged(self):
        diff = (
            "+++ b/app.py\n"
            "@@ -5,2 +5,1 @@\n"
            "-OPENAI_KEY = 'sk-proj-98347109283740192830192380129381'\n"
            "+OPENAI_KEY = os.environ.get('OPENAI_KEY')\n"
        )
        findings = scan_diff_text(diff)
        self.assertEqual(len(findings), 0)

    def test_lockfile_and_minified_assets_skipped(self):
        diff = (
            "+++ b/package-lock.json\n"
            "@@ -1,1 +1,2 @@\n"
            '+"integrity": "sha512-d41d8cd98f00b204e9800998ecf8427e98a1234567890abcdef1234567890abcdef=="\n'
            "+++ b/bundle.min.js\n"
            "@@ -1,1 +1,2 @@\n"
            '+var _0x123="d41d8cd98f00b204e9800998ecf8427e98a123456789";\n'
        )
        findings = scan_diff_text(diff)
        self.assertEqual(len(findings), 0)
        self.assertTrue(should_skip_file("package-lock.json"))
        self.assertTrue(should_skip_file("dist/bundle.min.js"))

    def test_test_fixtures_classified_as_mock(self):
        diff = (
            "+++ b/tests/unit/test_auth.py\n"
            "@@ -10,1 +10,2 @@\n"
            "+DUMMY_TOKEN = 'sk-proj-123456789012345678901234567890'\n"
        )
        findings = scan_diff_text(diff)
        self.assertEqual(len(findings), 1)
        self.assertTrue(findings[0].is_test_context)

    def test_ast_python_test_suite_detection(self):
        # Genuine AST detection of unittest.TestCase
        unittest_code = "import unittest\nclass AuthTest(unittest.TestCase):\n    pass\n"
        self.assertTrue(is_python_test_ast(unittest_code))

        # Genuine AST detection of pytest functions
        pytest_code = "def test_login_flow():\n    assert True\n"
        self.assertTrue(is_python_test_ast(pytest_code))

        # Regular non-test production code
        prod_code = "def process_payment(amount):\n    return amount * 1.05\n"
        self.assertFalse(is_python_test_ast(prod_code))

    def test_ast_docstring_aware_import_insertion(self):
        # Module with shebang and multiline docstring
        content = (
            "#!/usr/bin/env python3\n"
            '"""\n'
            "Database connection manager module.\n"
            '"""\n'
            "DB_HOST = 'localhost'\n"
        )
        new_content = insert_python_import_os(content)
        lines = new_content.splitlines()
        self.assertEqual(lines[0], "#!/usr/bin/env python3")
        self.assertEqual(lines[1], '"""')
        self.assertEqual(lines[2], "Database connection manager module.")
        self.assertEqual(lines[3], '"""')
        self.assertEqual(lines[4], "import os")

    def test_short_and_edge_case_masking(self):
        # 6 chars or less -> full redaction
        self.assertEqual(mask_secret("12345"), "********")
        # 7-8 chars -> full redaction
        self.assertEqual(mask_secret("1234567"), "********")
        self.assertEqual(mask_secret("12345678"), "********")
        # 9-16 chars -> 2 chars at start and end
        self.assertEqual(mask_secret("123456789012"), "12...12")
        # > 16 chars -> 3 chars at start and end
        self.assertEqual(mask_secret("sk-proj-1234567890abcdef1234567890"), "sk-...890")

    def test_shebang_preserved_when_import_os_inserted(self):
        content = "#!/usr/bin/env python3\nAPI_KEY = 'sk-123'\n"
        new_content = insert_python_import_os(content)
        lines = new_content.splitlines()
        self.assertEqual(lines[0], "#!/usr/bin/env python3")
        self.assertEqual(lines[1], "import os")

    def test_format_env_value_escaping(self):
        raw = 'val"with"quotes\\and\\slashes'
        formatted = format_env_value(raw)
        self.assertEqual(formatted, '"val\\"with\\"quotes\\\\and\\\\slashes"')

    def test_shannon_entropy_calculation(self):
        low = calculate_shannon_entropy("aaaaaaaaaaaaaaaaaaaa")
        self.assertAlmostEqual(low, 0.0)
        high = calculate_shannon_entropy("c2VjcmV0X3Rva2VuXzEyMzQ1Njc4OTA=")
        self.assertGreater(high, 3.5)

    def test_multiline_split_secret_detected(self):
        """
        Tests that scan_multiline_block reassembles adjacent added lines and finds
        an OpenAI key that spans two concatenated string fragments.
        """
        block_lines = [
            (10, "API_KEY = 'sk-proj-ABCDE"),
            (11, "FGHIJKLMNOPQRSTUVWXYZ1234'"),
        ]
        already_matched = set()
        from main import scan_multiline_block
        multi_findings = scan_multiline_block(block_lines, "app/config.py", already_matched)
        self.assertGreater(len(multi_findings), 0)
        self.assertIn("OpenAI API Key", multi_findings[0].pattern_name)
        self.assertIn("Multi-Line Split", multi_findings[0].pattern_name)

    def test_base64_encoded_secret_detected(self):
        """try_decode_base64_secret decodes a Base64 AWS key and returns the correct label."""
        import base64
        raw_secret = "AKIAIOSFODNN7ABCDEF12"
        encoded = base64.b64encode(raw_secret.encode()).decode()
        encoded = encoded + "=" * ((4 - len(encoded) % 4) % 4)
        b64_finding = try_decode_base64_secret(encoded)
        self.assertIsNotNone(b64_finding)
        self.assertIn("AWS Access Key", b64_finding[0])
        self.assertIn("Base64 Encoded", b64_finding[0])


if __name__ == "__main__":
    unittest.main()
