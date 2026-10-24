"""Tests for the facts read from code: outlines, settings and the import diagram.

Run from agents/readme-drafter:  python -m unittest discover -s tests -v
"""

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from readme_drafter.code_facts import find_settings, import_diagram, is_test_file, outline  # noqa: E402


def diagram_edges(diagram: str) -> set[tuple[str, str]]:
    nodes = dict(re.findall(r'(n\d+)\["([^"]+)"\]', diagram))
    return {(nodes[a], nodes[b]) for a, b in re.findall(r"(n\d+) --> (n\d+)", diagram)}


class OutlineTests(unittest.TestCase):
    def test_python_outline_keeps_declarations_and_drops_bodies(self):
        source = '''"""Serves the demo API."""
import os

SECRET_SAUCE = "kept out of outlines"

@app.get("/users")
def list_users(limit: int = 10) -> list:
    """Lists users. More text here."""
    return db.query(SECRET_SAUCE)

def _private():
    pass

class Store(Base):
    """Keeps users."""
    def add(self, user):
        return 1
    def _hidden(self):
        pass

if __name__ == "__main__":
    parser.add_argument("--port", type=int, default=8000)
'''
        text = outline("api/app.py", source)
        self.assertTrue(text.startswith("== api/app.py ==\n"))
        self.assertIn('"""Serves the demo API."""', text)
        self.assertIn("@app.get('/users')", text)
        self.assertIn("def list_users(limit: int=10) -> list  # Lists users", text)
        self.assertIn("class Store(Base)  # Keeps users.", text)
        self.assertIn("    def add(self, user)", text)
        self.assertIn('if __name__ == "__main__": runs as a script', text)
        self.assertIn('parser.add_argument("--port", type=int, default=8000)', text)
        for hidden in ("_private", "_hidden", "db.query", "SECRET_SAUCE"):
            self.assertNotIn(hidden, text)

    def test_typescript_outline_uses_declarations_and_doc_comments(self):
        source = """// Routes for the user API.
import express from 'express';

/**
 * Fetches all users.
 * @param req the request
 */
export async function getUsers(req, res) {
  const rows = await db.all();
}

export const addUser = async (req, res) => {
  return 1;
};

export interface User { id: number }
router.get('/users', getUsers);
"""
        text = outline("src/routes.ts", source)
        self.assertIn("// Routes for the user API.", text)
        self.assertIn("export async function getUsers(req, res)  // Fetches all users.", text)
        self.assertIn("export const addUser = async (req, res) =>", text)
        self.assertIn("export interface User", text)
        self.assertIn("router.get('/users', getUsers);", text)
        self.assertNotIn("db.all", text)

    def test_go_and_java_outlines(self):
        go = outline("cmd/server/main.go", "package main\n\n// Run starts the server.\nfunc Run(addr string) error {\n\treturn nil\n}\n\ntype Config struct {\n\tPort int\n}\n")
        self.assertIn("func Run(addr string) error  // Run starts the server.", go)
        self.assertIn("type Config struct", go)
        java = outline(
            "src/main/java/com/example/App.java",
            "package com.example;\n\npublic class App {\n    public static void main(String[] args) {\n        System.out.println(1);\n    }\n}\n",
        )
        self.assertIn("public class App", java)
        self.assertIn("public static void main(String[] args)", java)
        self.assertNotIn("println", java)

    def test_license_headers_and_minified_lines_are_skipped(self):
        text = outline("lib.js", "// Copyright 2026 Example Inc. All rights reserved.\n// Formats dates for the UI.\n" + "x" * 600 + "\n")
        self.assertIn("// Formats dates for the UI.", text)
        self.assertNotIn("Copyright", text)
        self.assertNotIn("xxxx", text)


class SettingsTests(unittest.TestCase):
    def test_settings_are_found_with_defaults_across_languages(self):
        files = [
            ("app/config.py", 'PORT = int(os.getenv("PORT", "8000"))\nDB = os.environ["DATABASE_URL"]\n'
                              'os.environ.setdefault("MODE", "dev")\nNAME = os.getenv("APP_NAME") or "demo"\n'),
            ("web/server.ts", "const host = process.env.HOST || 'localhost';\nconst key = process.env['STRIPE_KEY'];\n"),
            ("cmd/main.go", 'addr := os.Getenv("LISTEN_ADDR")\n'),
            ("src/main.rs", 'let level = env::var("RUST_LOG").unwrap_or("info".to_string());\n'),
            ("app/Config.java", 'String region = System.getenv("AWS_REGION");\n'),
            ("config/app.rb", 'ENV.fetch("SECRET_KEY_BASE")\nENV["RACK_ENV"] || "development"\n'),
            ("docker-compose.yml", "services:\n  app:\n    environment:\n      TOKEN_TTL: ${TOKEN_TTL:-3600}\n      REGION: ${REGION:?set REGION}\n"),
            ("tests/test_config.py", 'os.getenv("ONLY_IN_TESTS")\n'),
            ("app/paths.py", 'os.getenv("HOME")\n'),
        ]
        settings = {s["name"]: s for s in find_settings(files)}
        self.assertEqual(settings["PORT"]["default"], "8000")
        self.assertTrue(settings["DATABASE_URL"]["required"])
        self.assertEqual(settings["MODE"]["default"], "dev")
        self.assertEqual(settings["APP_NAME"]["default"], "demo")
        self.assertEqual(settings["HOST"]["default"], "localhost")
        self.assertIn("STRIPE_KEY", settings)
        self.assertEqual(settings["LISTEN_ADDR"]["read_in"], ["cmd/main.go"])
        self.assertEqual(settings["RUST_LOG"]["default"], "info")
        self.assertIn("AWS_REGION", settings)
        self.assertTrue(settings["SECRET_KEY_BASE"]["required"])
        self.assertEqual(settings["RACK_ENV"]["default"], "development")
        self.assertEqual(settings["TOKEN_TTL"]["default"], "3600")
        self.assertTrue(settings["REGION"]["required"])
        self.assertFalse(settings["PORT"]["required"])
        self.assertNotIn("ONLY_IN_TESTS", settings)
        self.assertNotIn("HOME", settings)

    def test_secret_defaults_are_hidden(self):
        files = [("app.py", 'KEY = os.getenv("API_KEY", "abc123secretvalue")\nT = os.getenv("MAX_TOKENS", "4096")\n')]
        settings = {s["name"]: s for s in find_settings(files)}
        self.assertEqual(settings["API_KEY"]["default"], "[REDACTED]")
        self.assertEqual(settings["MAX_TOKENS"]["default"], "4096")


class DiagramTests(unittest.TestCase):
    def test_python_and_typescript_imports_become_a_mermaid_graph(self):
        files = [
            ("app/__init__.py", "from . import cli\n"),
            ("app/cli.py", "import json\nfrom app.core import run\nfrom .db import connect\n"),
            ("app/core.py", "from . import db\n"),
            ("app/db.py", "import sqlite3\n"),
            ("web/main.ts", "import { api } from './api.js';\nimport express from 'express';\n"),
            ("web/api.ts", "export const api = 1;\n"),
            ("tests/test_cli.py", "from app import cli\n"),
        ]
        diagram = import_diagram(files, [path for path, _ in files])
        self.assertTrue(diagram.startswith("graph TD"))
        self.assertEqual(diagram_edges(diagram), {
            ("app/__init__.py", "app/cli.py"), ("app/cli.py", "app/core.py"), ("app/cli.py", "app/db.py"),
            ("app/core.py", "app/db.py"), ("web/main.ts", "web/api.ts"),
        })

    def test_go_imports_and_hostile_file_names(self):
        files = [
            ("cmd/server/main.go", 'package main\nimport (\n\t"fmt"\n\t"example.com/demo/internal/store"\n)\n'),
            ("internal/store/store.go", "package store\n"),
            ('evil"]-->x[click.js', "import './b.js'\n"),
            ("b.js", ""),
        ]
        diagram = import_diagram(files, [path for path, _ in files], go_module="example.com/demo")
        self.assertIn(("cmd/server/main.go", "internal/store/store.go"), diagram_edges(diagram))
        self.assertNotIn('"]-->x[', diagram)

    def test_big_projects_are_drawn_per_folder(self):
        sources = {}
        for folder in ("api", "core", "db", "web"):
            sources[f"{folder}/__init__.py"] = ""
        for i in range(4):
            sources[f"api/m{i}.py"] = f"from core import m{i}\n"
            sources[f"core/m{i}.py"] = f"from db import m{i}\n"
            sources[f"db/m{i}.py"] = ""
            sources[f"web/m{i}.py"] = f"from api import m{i}\n"
        diagram = import_diagram(list(sources.items()), list(sources))
        self.assertEqual(diagram_edges(diagram), {("api/", "core/"), ("core/", "db/"), ("web/", "api/")})

    def test_no_internal_imports_means_no_diagram(self):
        self.assertIsNone(import_diagram([("main.py", "import os\n")], ["main.py"]))

    def test_test_files_are_recognised(self):
        for path in ("tests/test_x.py", "test_x.py", "src/app.test.ts", "pkg/x_test.go", "lib/a_spec.rb", "conftest.py"):
            self.assertTrue(is_test_file(path), path)
        for path in ("src/contest.py", "latest.py", "testing_utils.py", "src/app.ts"):
            self.assertFalse(is_test_file(path), path)


if __name__ == "__main__":
    unittest.main()
