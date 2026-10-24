import json
import sys

from dead_code_reaper.cli import main

PYTEST = f"{sys.executable} -m pytest -q -p no:cacheprovider"

FILES = {
    "pkg/__init__.py": "",
    "pkg/core.py": """
        import os


        def used():
            return 1


        def old():
            return _helper()


        def _helper():
            return 2
    """,
    "tests/test_core.py": "from pkg.core import used\n\n\ndef test_used():\n    assert used() == 1\n",
}


def run(root, monkeypatch, *extra):
    for key in ("GEMINI_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENAI_BASE_URL"):
        monkeypatch.delenv(key, raising=False)
    return main(["run", str(root), "--app", "--test-cmd", PYTEST, *extra])


def test_run_then_apply(make_project, monkeypatch):
    root = make_project(FILES)
    assert run(root, monkeypatch) == 0
    report = (root / "reaper-out" / "report.html").read_text()
    assert "Dead code in proj" in report and '"number": 1' in report
    data = json.loads((root / "reaper-out" / "report.json").read_text())
    assert len(data["removals"]) == 3
    assert main(["apply", str(root)]) == 0
    assert (root / "pkg" / "core.py").read_text() == "def used():\n    return 1\n"
    assert "deleted" not in (root / "reaper-out" / "applied.patch").read_text()


def test_apply_keep_pulls_in_dependencies(make_project, monkeypatch, capsys):
    root = make_project(FILES)
    run(root, monkeypatch)
    data = json.loads((root / "reaper-out" / "report.json").read_text())
    old = next(r["number"] for r in data["removals"] if r["name"] == "old")
    assert main(["apply", str(root), "--keep", str(old)]) == 0
    text = (root / "pkg" / "core.py").read_text()
    assert "def old" in text and "def _helper" in text and "import os" not in text
    assert "also keeping" in capsys.readouterr().out


def test_apply_refuses_changed_files(make_project, monkeypatch):
    root = make_project(FILES)
    run(root, monkeypatch)
    (root / "pkg" / "core.py").write_text("x = 1\n")
    assert main(["apply", str(root)]) == 2


def test_dry_run_changes_nothing(make_project, monkeypatch):
    root = make_project(FILES)
    run(root, monkeypatch)
    before = (root / "pkg" / "core.py").read_text()
    assert main(["apply", str(root), "--dry-run"]) == 0
    assert (root / "pkg" / "core.py").read_text() == before
    assert (root / "reaper-out" / "applied.patch").read_text().startswith("diff --git")


def test_scan_writes_read_only_report(make_project):
    root = make_project(FILES)
    assert main(["scan", str(root), "--app"]) == 0
    assert '"readonly": true' in (root / "reaper-out" / "report.html").read_text()
