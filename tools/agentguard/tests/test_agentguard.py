import tempfile
import unittest
from pathlib import Path

from agentguard import scan_path


class AgentGuardTests(unittest.TestCase):
    def test_detects_request_without_timeout(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "app.py").write_text("import requests\nrequests.get('https://example.com')\n", encoding="utf-8")
            findings = scan_path(Path(tmp))
            self.assertIn("AG101", {f.rule for f in findings})

    def test_accepts_request_with_timeout(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "app.py").write_text("import requests\nrequests.get('https://example.com', timeout=5)\n", encoding="utf-8")
            findings = scan_path(Path(tmp))
            self.assertNotIn("AG101", {f.rule for f in findings})

    def test_detects_dynamic_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "agent.py").write_text("def run_agent(code):\n    exec(code)\n", encoding="utf-8")
            findings = scan_path(Path(tmp))
            self.assertIn("AG201", {f.rule for f in findings})

    def test_skips_virtual_environments(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".venv").mkdir()
            (root / ".venv" / "bad.py").write_text("while True: pass\n", encoding="utf-8")
            self.assertEqual(scan_path(root), [])


if __name__ == "__main__":
    unittest.main()
