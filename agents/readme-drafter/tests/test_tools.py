"""Tests for the drafter's tools. They need no model and no network.

Run from agents/readme-drafter:  python -m unittest discover -s tests -v
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from readme_drafter.tools import (  # noqa: E402
    detect_project_stack,
    extract_readme,
    list_project_files,
    read_file,
    read_key_files,
    save_readme_draft,
)

FAKE_KEY = "sk-" + "a1b2c3d4e5f6g7h8i9j0k1l2"


class ToolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "demo-project"
        (self.root / "src").mkdir(parents=True)
        (self.root / "node_modules" / "lib").mkdir(parents=True)
        (self.root / "main.py").write_text(f'API_KEY = "{FAKE_KEY}"\nprint("hello")\n')
        (self.root / "src" / "helpers.py").write_text("def add(a, b):\n    return a + b\n")
        (self.root / "node_modules" / "lib" / "index.js").write_text("module.exports = 1;\n")
        (self.root / ".env").write_text(f"OPENAI_API_KEY={FAKE_KEY}\n")
        (self.root / "server.pem").write_text("-----BEGIN PRIVATE KEY-----\n")
        (self.root / ".env.example").write_text("OPENAI_API_KEY=your_key_here\n# PORT=8080\n")
        (self.root / "requirements.txt").write_text("# deps\nrequests==2.32.3\nrich\n")
        (self.root / "package.json").write_text(
            json.dumps({"name": "demo", "scripts": {"start": "node index.js"}, "dependencies": {"express": "^4"}})
        )
        (Path(self.tmp.name) / "outside.txt").write_text("not part of the project\n")
        self.env = mock.patch.dict(
            os.environ, {"PROJECT_DIR": str(self.root), "OUTPUT_DIR": str(Path(self.tmp.name) / "out")}
        )
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_list_hides_secrets_and_dependency_folders(self):
        result = list_project_files()
        self.assertEqual(result["status"], "success")
        self.assertIn("main.py", result["files"])
        self.assertIn("src/helpers.py", result["files"])
        self.assertIn(".env.example", result["files"])
        self.assertNotIn(".env", result["files"])
        self.assertNotIn("server.pem", result["files"])
        self.assertFalse(any(f.startswith("node_modules") for f in result["files"]))
        self.assertEqual(result["unreadable_files_hidden"], 2)

    def test_list_respects_max_depth(self):
        self.assertNotIn("src/helpers.py", list_project_files(max_depth=1)["files"])

    def test_read_refuses_secret_files(self):
        for name in (".env", "server.pem"):
            result = read_file(name)
            self.assertEqual(result["status"], "error", name)
            self.assertNotIn("content", result)

    def test_read_refuses_paths_outside_project(self):
        for path in ("../outside.txt", str(Path(self.tmp.name) / "outside.txt"), "/etc/hosts"):
            self.assertEqual(read_file(path)["status"], "error", path)

    def test_read_refuses_symlink_escaping_project(self):
        (self.root / "link.txt").symlink_to(Path(self.tmp.name) / "outside.txt")
        self.assertEqual(read_file("link.txt")["status"], "error")

    def test_read_redacts_token_like_strings(self):
        result = read_file("main.py")
        self.assertEqual(result["status"], "success")
        self.assertNotIn(FAKE_KEY, result["content"])
        self.assertIn("[REDACTED]", result["content"])

    def test_detect_stack_reads_manifests_but_not_env_values(self):
        result = detect_project_stack()
        manifests = result["manifests"]
        self.assertEqual(manifests["requirements.txt"]["dependencies"], ["requests==2.32.3", "rich"])
        self.assertEqual(manifests["package.json"]["scripts"], {"start": "node index.js"})
        self.assertEqual(manifests[".env.example"]["variables"], ["OPENAI_API_KEY"])
        self.assertEqual(manifests[".env.example"]["commented_out_variables"], ["PORT"])
        self.assertNotIn("your_key_here", json.dumps(result))
        self.assertIn("Python", result["languages_by_file_count"])
        self.assertIn("main.py", result["likely_entry_points"])
        self.assertIsNone(result["license"]["detected"])

    def test_detect_stack_names_common_licenses(self):
        (self.root / "LICENSE").write_text("Copyright (c) 2026 Demo\n\nPermission is hereby granted, free of charge, to any person")
        self.assertEqual(detect_project_stack()["license"], {
            "file": "LICENSE", "detected": "MIT", "excerpt": "Copyright (c) 2026 Demo Permission is hereby granted, free of charge, to any person",
        })

    def test_read_key_files_picks_code_and_skips_secrets(self):
        result = read_key_files()
        self.assertEqual(list(result["files"])[0], "main.py")
        self.assertIn("src/helpers.py", result["files"])
        self.assertNotIn(".env", result["files"])
        self.assertFalse(any(p.startswith("node_modules") for p in result["files"]))
        self.assertNotIn(FAKE_KEY, json.dumps(result))

    def test_extract_readme_drops_intro_and_leaked_tokens(self):
        reply = "I read 6 files. I will now write the markdown.# demo\n> Does things.\n## Overview\nText<channel|>"
        self.assertEqual(extract_readme(reply), "# demo\n> Does things.\n## Overview\nText\n")

    def test_extract_readme_ignores_replies_without_sections(self):
        self.assertIsNone(extract_readme("Sure, which folder should I look at?"))
        self.assertIsNone(extract_readme("## Overview only, no title"))

    def test_save_writes_draft_and_redacts(self):
        result = save_readme_draft(f"# Demo\n\nKey: {FAKE_KEY}\n")
        saved = Path(result["saved_to"]).read_text()
        self.assertTrue(saved.startswith("# Demo"))
        self.assertNotIn(FAKE_KEY, saved)


if __name__ == "__main__":
    unittest.main()
