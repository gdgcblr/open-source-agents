import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from securevantara.__main__ import main
from securevantara.agent import SecurityReviewAgent, run_agent


class SecurityReviewAgentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_initialization_validation(self):
        with self.assertRaises(ValueError):
            SecurityReviewAgent(self.root, provider="unsupported")
        with self.assertRaises(ValueError):
            SecurityReviewAgent(self.root, timeout=0)
        with self.assertRaises(ValueError):
            SecurityReviewAgent(self.root, timeout=301)

        agent = SecurityReviewAgent(self.root, provider="gemini")
        self.assertEqual(agent.model, "gemini-2.5-flash")

        agent_ollama = SecurityReviewAgent(self.root, provider="ollama")
        self.assertEqual(agent_ollama.model, "gemma4:e4b")

    def test_discovery_and_bounds(self):
        (self.root / "valid.py").write_text("x = 1\n")
        (self.root / "large.py").write_text("x = 1\n" * 5000)
        (self.root / "ignored.txt").write_text("ignored\n")
        sub = self.root / ".venv"
        sub.mkdir()
        (sub / "hidden.py").write_text("y = 2\n")

        agent = SecurityReviewAgent(self.root, provider="mock", max_file_size=100)
        sources, skipped = agent.discover()
        self.assertIn("valid.py", sources)
        self.assertNotIn("ignored.txt", sources)
        self.assertIn("large.py", skipped)
        self.assertNotIn(".venv/hidden.py", sources)

    def test_mock_provider_full_lifecycle(self):
        (self.root / "sample.py").write_text("def test(x):\n    return eval(x)\n")
        agent = SecurityReviewAgent(self.root, provider="mock", remediate=True)
        report = agent.run()

        self.assertEqual(report["errors"], [])
        self.assertGreaterEqual(len(report["findings"]), 1)
        for finding in report["findings"]:
            self.assertIn("remediation", finding)
            self.assertIn("safer_alternative", finding)
            self.assertIn("ast.literal_eval", finding["remediation"])

        meta = report["agent"]
        self.assertEqual(meta["provider"], "mock")
        self.assertEqual(meta["metrics"]["files_reviewed"], 1)
        self.assertIn(meta["metrics"]["risk_posture"], {"High", "Informational", "Medium"})
        self.assertIn("sample.py", meta["reviewed_files"])

    def test_remediation_disabled(self):
        (self.root / "sample.py").write_text("eval(x)\n")
        agent = SecurityReviewAgent(self.root, provider="mock", remediate=False)
        report = agent.run()
        self.assertGreaterEqual(len(report["findings"]), 1)
        for finding in report["findings"]:
            self.assertNotIn("remediation", finding)

    def test_gemini_missing_api_key(self):
        (self.root / "sample.py").write_text("eval(x)\n")
        with patch.dict("os.environ", {}, clear=True):
            agent = SecurityReviewAgent(self.root, provider="gemini", api_key=None)
            report = agent.run()
            self.assertTrue(any("GEMINI_API_KEY" in err for err in report["errors"]))

    def test_gemini_mocked_success(self):
        (self.root / "sample.py").write_text("eval(x)\n")
        candidate_payload = json.dumps({"findings": [{
            "path": "sample.py",
            "line": 1,
            "title": "Unsafe Dynamic Evaluation",
            "evidence": "eval(x)",
            "severity": "high"
        }]})
        envelope = {
            "candidates": [{
                "content": {
                    "parts": [{"text": candidate_payload}]
                }
            }]
        }
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(envelope).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            agent = SecurityReviewAgent(self.root, provider="gemini", api_key="test-key")
            report = agent.run()
            self.assertEqual(report["errors"], [])
            gemini_findings = [f for f in report["findings"] if any(p.get("engine") == "gemini" for p in f["provenance"])]
            self.assertEqual(len(gemini_findings), 1)
            self.assertEqual(gemini_findings[0]["status"], "unverified")
            self.assertIn("ast.literal_eval", gemini_findings[0]["remediation"])

    def test_gemini_response_size_limit(self):
        (self.root / "sample.py").write_text("eval(x)\n")
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"x" * 262145
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            agent = SecurityReviewAgent(self.root, provider="gemini", api_key="test-key")
            report = agent.run()
            self.assertTrue(any("exceeds 256 KiB" in err for err in report["errors"]))

    def test_ollama_provider_delegation(self):
        (self.root / "sample.py").write_text("eval(x)\n")
        mock_res = {
            "findings": [{
                "id": "abc", "rule": "llm.review", "path": "sample.py", "line": 1,
                "evidence": "eval(x)", "severity": "high", "kind": "source-review",
                "status": "unverified", "title": "Dynamic eval",
                "provenance": [{"engine": "ollama", "model": "gemma4:e4b"}]
            }],
            "error": None
        }
        with patch("securevantara.agent.review", return_value=mock_res):
            agent = SecurityReviewAgent(self.root, provider="ollama")
            report = agent.run()
            self.assertEqual(report["errors"], [])
            self.assertGreaterEqual(len(report["findings"]), 1)

    def test_agent_cli_command(self):
        (self.root / "sample.py").write_text("eval(x)\n")
        report_file = self.root / "agent_report.json"
        exit_code = main([
            "agent",
            "--source", str(self.root),
            "--scope", str(self.root),
            "--authorized",
            "--provider", "mock",
            "--report", str(report_file)
        ])
        self.assertEqual(exit_code, 0)
        self.assertTrue(report_file.exists())
        self.assertEqual(report_file.stat().st_mode & 0o777, 0o600)

        data = json.loads(report_file.read_text(encoding="utf-8"))
        self.assertEqual(data["operation"], "agent")
        self.assertEqual(data["schema_version"], "1.0")
        self.assertIn("agent", data)
        self.assertEqual(data["agent"]["provider"], "mock")
        self.assertGreaterEqual(len(data["findings"]), 1)
        self.assertIn("remediation", data["findings"][0])

    def test_agent_cli_requires_auth(self):
        (self.root / "sample.py").write_text("eval(x)\n")
        report_file = self.root / "denied_report.json"
        exit_code = main([
            "agent",
            "--source", str(self.root),
            "--scope", str(self.root),
            "--provider", "mock",
            "--report", str(report_file)
        ])
        self.assertEqual(exit_code, 2)
        data = json.loads(report_file.read_text(encoding="utf-8"))
        self.assertTrue(data["errors"])


if __name__ == "__main__":
    unittest.main()
