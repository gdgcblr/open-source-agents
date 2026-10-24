from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from repro_capsule.capsule import load_capsule, make_capsule, save_capsule
from repro_capsule.cli import main
from repro_capsule.model import investigate
from repro_capsule.sandbox import (
    OUTPUT_LIMIT,
    SandboxError,
    TestResult,
    _drain_bounded,
    docker_command,
    run_tests,
)
from repro_capsule.tools import list_files, read_file


class RepoToolsTests(unittest.TestCase):
    def test_read_file_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "repo"
            root.mkdir()
            outside = Path(temp) / "secret.txt"
            outside.write_text("secret", encoding="utf-8")
            with self.assertRaises(ValueError):
                read_file(root, "../secret.txt")

    def test_file_listing_skips_git_metadata(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / ".git").mkdir()
            (root / ".git" / "config").write_text("ignore", encoding="utf-8")
            (root / "README.md").write_text("hi", encoding="utf-8")
            self.assertEqual(list_files(root), ["README.md"])
            with self.assertRaisesRegex(ValueError, "metadata"):
                read_file(root, ".git/config")

    def test_credential_files_are_neither_listed_nor_readable(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "README.md").write_text("hello", encoding="utf-8")
            (root / ".env.local").write_text("TOKEN=secret", encoding="utf-8")
            (root / ".aws").mkdir()
            (root / ".aws" / "credentials").write_text("secret", encoding="utf-8")
            (root / "id_ed25519").write_text("private key", encoding="utf-8")
            self.assertEqual(list_files(root), ["README.md"])
            with self.assertRaisesRegex(ValueError, "Credential-like"):
                read_file(root, ".env.local")
            with self.assertRaisesRegex(ValueError, "Credential-like"):
                read_file(root, ".aws/credentials")
            with self.assertRaisesRegex(ValueError, "Credential-like"):
                read_file(root, "id_ed25519")


class ModelTests(unittest.TestCase):
    @patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"})
    @patch("repro_capsule.model._generate")
    def test_model_only_gets_allowlisted_read_tools(self, generate):
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            (repo / "README.md").write_text("timeout bug", encoding="utf-8")
            generate.side_effect = [
                {"candidates": [{"content": {"parts": [
                    {"functionCall": {"name": "run_shell", "args": {"command": "whoami"}}},
                ]}}]},
                {"candidates": [{"content": {"parts": [{"text": "I could not run commands."}]}}]},
            ]
            answer = investigate("A test bug", repo)
        self.assertEqual(answer, "I could not run commands.")
        self.assertEqual(generate.call_count, 2)
        response = generate.call_args_list[1].args[2]["contents"][-2]["parts"][0]
        self.assertEqual(
            response["functionResponse"]["response"]["result"],
            {"error": "Tool is not allowlisted."},
        )


class SandboxTests(unittest.TestCase):
    def test_execution_is_blocked_without_opt_in(self):
        with tempfile.TemporaryDirectory() as temp:
            result = run_tests(Path(temp), allow_execution=False)
            self.assertEqual(result.status, "blocked")

    def test_docker_command_is_fixed_and_restrictive(self):
        with tempfile.TemporaryDirectory() as temp:
            command = docker_command(Path(temp))
            self.assertEqual(command[-5:], ["python:3.12-slim", "python", "-m", "unittest", "discover", "-v"][-5:])
            self.assertIn("--network=none", command)
            self.assertIn("--read-only", command)
            self.assertIn("readonly", command[command.index("--mount") + 1])
            self.assertNotIn("shell", command)

    @patch("repro_capsule.sandbox.shutil.which", return_value="docker")
    @patch("repro_capsule.sandbox.subprocess.Popen")
    def test_runner_invokes_docker_without_shell(self, popen, _which):
        popen.return_value = SimpleNamespace(
            stdout=BytesIO(), stderr=BytesIO(), returncode=1, wait=Mock(return_value=1),
        )
        with tempfile.TemporaryDirectory() as temp:
            result = run_tests(Path(temp), allow_execution=True)
        self.assertEqual(result.status, "failed")
        self.assertFalse(popen.call_args.kwargs["shell"])
        self.assertEqual(popen.call_args.args[0][0:3], ["docker", "run", "--rm"])

    def test_captured_child_output_is_bounded(self):
        output = []
        _drain_bounded(BytesIO(b"x" * (OUTPUT_LIMIT + 20) + b"end"), output)
        self.assertEqual(len(output[0].encode()), OUTPUT_LIMIT)
        self.assertTrue(output[0].endswith("end"))

    @patch("repro_capsule.sandbox.shutil.which", return_value="docker")
    @patch("repro_capsule.sandbox.subprocess.run")
    @patch("repro_capsule.sandbox.subprocess.Popen")
    def test_timeout_stops_the_named_container(self, popen, stop, _which):
        process = SimpleNamespace(
            stdout=BytesIO(), stderr=BytesIO(), returncode=0,
            wait=Mock(side_effect=[
                subprocess.TimeoutExpired("docker", 120), 0,
            ]),
            kill=Mock(),
        )
        popen.return_value = process
        with tempfile.TemporaryDirectory() as temp:
            result = run_tests(Path(temp), allow_execution=True)
        self.assertEqual(result.status, "timeout")
        self.assertIsNone(result.exit_code)
        self.assertEqual(stop.call_args.args[0][0:4], ["docker", "stop", "--time", "1"])
        process.kill.assert_not_called()

    @patch.dict("os.environ", {"REPRO_CAPSULE_DOCKER_BIN": r"C:\Docker\docker.exe"})
    def test_docker_command_uses_launcher_resolved_binary(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(docker_command(Path(temp))[0], r"C:\Docker\docker.exe")

    @patch("repro_capsule.sandbox.shutil.which", return_value=None)
    def test_missing_docker_fails_with_setup_help(self, _which):
        with tempfile.TemporaryDirectory() as temp, self.assertRaisesRegex(SandboxError, "pre-pull"):
            run_tests(Path(temp), allow_execution=True)


class CapsuleTests(unittest.TestCase):
    def test_capsule_round_trip_and_command_tamper_rejection(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            result = TestResult("failed", 1, "", "failure")
            capsule = make_capsule(root, "report", result)
            destination = root / "capsule.json"
            save_capsule(capsule, destination)
            self.assertEqual(load_capsule(destination)["execution"]["status"], "failed")
            data = json.loads(destination.read_text(encoding="utf-8"))
            data["execution"]["command"] = ["python", "-c", "import os; os.remove('x')"]
            destination.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "fixed runner"):
                load_capsule(destination)

    def test_local_demo_capsule_cannot_be_replayed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            result = TestResult("failed", 1, "", "expected demo failure", image=None)
            capsule = make_capsule(root, "demo", result, execution_mode="local_demo")
            destination = root / "demo.json"
            save_capsule(capsule, destination)
            with self.assertRaisesRegex(ValueError, "not replayable"):
                load_capsule(destination)

    @patch("repro_capsule.cli.run_tests")
    @patch("repro_capsule.cli.repository_revision", return_value="b" * 40)
    @patch("repro_capsule.cli.load_capsule")
    @patch("sys.argv", ["repro-capsule", "replay", "--repo", ".", "--capsule", "capsule.json", "--allow-execution"])
    def test_replay_blocks_revision_mismatch_before_execution(self, load, _revision, run_tests_mock):
        load.return_value = {
            "repository_revision": "a" * 40,
            "execution": {"status": "failed", "exit_code": 1},
        }
        self.assertEqual(main(), 2)
        run_tests_mock.assert_not_called()

    @patch("repro_capsule.cli.run_tests")
    @patch("repro_capsule.cli.repository_revision", return_value=None)
    @patch("repro_capsule.cli.load_capsule")
    @patch("sys.argv", ["repro-capsule", "replay", "--repo", ".", "--capsule", "capsule.json", "--allow-execution"])
    def test_replay_blocks_unverifiable_revision_before_execution(
        self, load, _revision, run_tests_mock,
    ):
        load.return_value = {
            "repository_revision": None,
            "execution": {"status": "failed", "exit_code": 1},
        }
        self.assertEqual(main(), 2)
        run_tests_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
