"""Tests for big-project mode: part planning, the summary cache and the ADK orchestration.

The orchestration tests run the real agent against a fake Ollama server on localhost
and check what each model request contained, so they need no model and no network.

Run from agents/readme-drafter:  python -m unittest discover -s tests -v
"""

import asyncio
import json
import os
import re
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from google.adk.runners import InMemoryRunner  # noqa: E402
from google.genai import types  # noqa: E402

from readme_drafter import agent, big_project, tools  # noqa: E402

FAKE_README = "# demo\n> A demo project.\n\n## Overview\nIt works.\n\n## Architecture & Data Flow\nParts talk.\n"


class FakeOllama:
    """Answers like Ollama's /api/chat and records every request it gets."""

    def __init__(self):
        self.requests = []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                fake.requests.append((self.path, body))
                if self.path.endswith("/api/chat"):
                    label = re.search(r"^<<<PART (.+)$", system_prompt(body), re.M)
                    text = f"Purpose: Handles {label.group(1)}.\nKey files: a.py - main file" if label else FAKE_README
                    payload = {"model": body.get("model"), "created_at": "2026-01-01T00:00:00Z", "done": True,
                               "done_reason": "stop", "message": {"role": "assistant", "content": text}}
                else:  # LiteLLM asks /api/show for model details
                    payload = {"capabilities": ["completion", "tools"], "model_info": {}, "details": {}}
                out = json.dumps(payload).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def chats(self, summaries: bool) -> list[dict]:
        return [body for path, body in self.requests
                if path.endswith("/api/chat") and ("<<<PART " in system_prompt(body)) == summaries]


def system_prompt(body: dict) -> str:
    return next((m.get("content") or "" for m in body.get("messages", []) if m["role"] == "system"), "")


def history(body: dict) -> str:
    return json.dumps([m for m in body["messages"] if m["role"] != "system"])


class PlanTests(unittest.TestCase):
    def test_parts_follow_folders_and_respect_the_size_limit(self):
        outlines = [(f"a/f{i}.py", "x" * 300) for i in range(5)] + [(f"b/g{i}.py", "y" * 300) for i in range(5)]
        with mock.patch.object(big_project, "PART_CHARS", 1000):
            parts, beyond = big_project.plan_parts(outlines)
        self.assertEqual(beyond, 0)
        self.assertEqual([len(p.files) for p in parts], [3, 2, 3, 2])
        self.assertEqual([p.label for p in parts], ["a/ (3 files)", "a/ part 2 (2 files)", "b/ (3 files)", "b/ part 2 (2 files)"])
        self.assertTrue(all(len(p.outline) <= 1000 for p in parts))

    def test_files_beyond_the_part_limit_are_counted(self):
        outlines = [(f"f{i}.py", "x" * 600) for i in range(6)]
        with mock.patch.object(big_project, "PART_CHARS", 1000), mock.patch.object(big_project, "MAX_PARTS", 2):
            parts, beyond = big_project.plan_parts(outlines)
        self.assertEqual((len(parts), beyond), (2, 4))

    def test_cache_key_changes_with_the_model_or_the_code(self):
        part = big_project.Part("a/ (1 file)", ("a/x.py",), "== a/x.py ==\ndef f()\n")
        key = big_project.cache_key("gemma4:e4b", part)
        self.assertEqual(key, big_project.cache_key("gemma4:e4b", part))
        self.assertNotEqual(key, big_project.cache_key("gemma4:12b", part))
        changed = big_project.Part(part.label, part.files, part.outline + "def g()\n")
        self.assertNotEqual(key, big_project.cache_key("gemma4:e4b", changed))

    def test_summaries_are_cleaned(self):
        reply = "Sure! Purpose: Stores users.\nKey files: db.py - saves rows\nBase every word on the outline.<channel|>"
        self.assertEqual(big_project.clean_summary(reply), "Purpose: Stores users.\nKey files: db.py - saves rows")
        self.assertEqual(big_project.clean_summary(""), big_project.NO_SUMMARY)

    def test_cache_survives_garbage_and_never_writes_through_a_link(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / big_project.CACHE_FILE).write_text("not json")
            self.assertEqual(big_project.load_cache(folder), {})
            victim = folder / "victim.txt"
            victim.write_text("keep me")
            (folder / big_project.CACHE_FILE).unlink()
            (folder / big_project.CACHE_FILE).symlink_to(victim)
            big_project.save_cache(folder, {"k": "v"})
            self.assertEqual(victim.read_text(), "keep me")
            self.assertEqual(big_project.load_cache(folder), {"k": "v"})


class OrchestrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # One event loop for every run: LiteLLM caches its HTTP client on the loop that created it.
        cls.loop = asyncio.new_event_loop()

    @classmethod
    def tearDownClass(cls):
        cls.loop.close()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.root, self.out = base / "demo", base / "out"
        for folder in ("pkg_a", "pkg_b"):
            (self.root / folder).mkdir(parents=True)
            (self.root / folder / "__init__.py").write_text("")
        (self.root / "main.py").write_text("from pkg_a import core\ncore.run(1)\n")
        (self.root / "pkg_a" / "core.py").write_text(
            '"""Core logic."""\nfrom pkg_b import store\n\ndef run(x):\n    """Runs one job."""\n    return store.save(x)\n'
        )
        (self.root / "pkg_b" / "store.py").write_text(
            '"""Saves jobs."""\nimport os\n\nDB = os.getenv("DB_PATH", "data.db")\n\ndef save(x):\n    """Saves one job."""\n    return x\n'
        )
        self.fake = FakeOllama()
        self.env = mock.patch.dict(os.environ, {
            "PROJECT_DIR": str(self.root), "OUTPUT_DIR": str(self.out),
            "OLLAMA_API_BASE": self.fake.url, "BIG_PROJECT_MODE": "1",
        })
        self.env.start()
        os.environ.pop("README_TEMPLATE", None)
        self.small_parts = mock.patch.object(big_project, "PART_CHARS", 150)  # several parts from a tiny project
        self.small_parts.start()
        self.parts, _ = big_project.plan_parts(tools.project_outlines()["outlines"])

    def tearDown(self):
        self.small_parts.stop()
        self.env.stop()
        self.fake.server.shutdown()
        self.fake.server.server_close()  # a late request must be refused, not left waiting forever
        self.tmp.cleanup()

    def run_agent(self, *messages: str) -> None:
        async def chat():
            runner = InMemoryRunner(agent=agent.root_agent, app_name="readme_drafter")
            session = await runner.session_service.create_session(app_name="readme_drafter", user_id="test")
            for text in messages:
                message = types.Content(role="user", parts=[types.Part(text=text)])
                async for _ in runner.run_async(user_id="test", session_id=session.id, new_message=message):
                    pass
        self.loop.run_until_complete(asyncio.wait_for(chat(), timeout=120))
        # LiteLLM logs each call in a background task that asks the server for model details;
        # let those finish while this test's fake server still answers.
        pending = asyncio.all_tasks(self.loop)
        if pending:
            self.loop.run_until_complete(asyncio.wait(pending, timeout=10))

    def test_each_part_is_summarised_alone_and_the_writer_gets_only_the_summaries(self):
        self.assertGreater(len(self.parts), 1)
        self.run_agent("Draft a README for this project.")
        summary_requests = self.fake.chats(summaries=True)
        self.assertEqual(len(summary_requests), len(self.parts))
        for request, part in zip(summary_requests, self.parts):
            prompt = system_prompt(request)
            for other in self.parts:
                for path in other.files:
                    self.assertEqual(f"== {path} ==" in prompt, other is part, path)
            self.assertNotIn("Purpose:", history(request))  # no earlier summary in its input

        [writer] = self.fake.chats(summaries=False)
        prompt = system_prompt(writer)
        self.assertIn("<<<PART_SUMMARIES", prompt)
        for part in self.parts:
            self.assertIn(f"Handles {part.label}", prompt)
        self.assertNotIn("Summarising part", history(writer))  # progress notes stay in their own branch
        self.assertNotIn("Purpose:", history(writer))

        draft = (self.out / "README.draft.md").read_text()
        self.assertIn("## Future Improvements", draft)  # added by the template check
        self.assertIn("```mermaid", draft)  # added from the imports

    def test_revisions_and_new_runs_reuse_the_saved_summaries(self):
        self.run_agent("Draft a README for this project.", "Make the overview shorter.")
        self.assertEqual(len(self.fake.chats(summaries=True)), len(self.parts))  # only the first turn summarised
        first, second = self.fake.chats(summaries=False)
        roles = [m["role"] for m in second["messages"] if m["role"] != "system"]
        self.assertEqual(roles, ["user", "assistant", "user"])  # the previous README is in the history
        self.assertIn("A demo project.", history(second))

        self.fake.requests.clear()
        self.run_agent("Draft a README for this project.")  # a new session: the cache file is used
        self.assertEqual(self.fake.chats(summaries=True), [])
        self.assertEqual(len(self.fake.chats(summaries=False)), 1)

    def test_normal_mode_makes_one_model_call_with_the_new_facts(self):
        with mock.patch.dict(os.environ, {"BIG_PROJECT_MODE": ""}):
            self.run_agent("Draft a README for this project.")
        self.assertEqual(self.fake.chats(summaries=True), [])
        [writer] = self.fake.chats(summaries=False)
        prompt = system_prompt(writer)
        self.assertNotIn("<<<PART_SUMMARIES", prompt)
        self.assertIn('"DB_PATH"', prompt)  # found in the code
        self.assertIn("## Future Improvements", prompt)  # the template is part of the prompt
        self.assertIn("graph TD", prompt)


if __name__ == "__main__":
    unittest.main()
