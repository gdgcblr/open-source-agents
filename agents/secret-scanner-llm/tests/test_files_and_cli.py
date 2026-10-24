import json
import subprocess

from secret_scanner.cli import main
from secret_scanner.files import IgnoreRules, is_test_path
from secret_scanner.scanner import collect_candidates

from . import helpers as H

LEAK = f'k = "{H.aws()}"\n'


def names(path, **kw):
    cands, stats = collect_candidates(path, **kw)
    return {c.file for c in cands}, stats


def test_skip_rules(tmp_path):
    for d in (".git", "node_modules", ".venv"):
        (tmp_path / d).mkdir()
        (tmp_path / d / "x.py").write_text(LEAK)
    (tmp_path / "package-lock.json").write_text(LEAK)
    (tmp_path / "big.txt").write_text(LEAK + "a" * 1_000_001)
    (tmp_path / "bin.dat").write_bytes(b"\x00\x01" + LEAK.encode())
    (tmp_path / "ok.py").write_text(LEAK)
    found, stats = names(tmp_path)
    assert found == {"ok.py"}
    assert stats["skipped_lockfile"] == 1 and stats["skipped_too_large"] == 1 and stats["skipped_binary"] == 1


def test_secretscanignore(tmp_path):
    (tmp_path / ".secretscanignore").write_text("# c\ndocs/\n*.sample\nconfig/dev.env\n")
    for rel in ("docs/a.md", "x.sample", "config/dev.env", "keep.py"):
        p = tmp_path / rel
        p.parent.mkdir(exist_ok=True, parents=True)
        p.write_text(LEAK)
    found, stats = names(tmp_path)
    assert found == {"keep.py"} and stats["skipped_ignored"] >= 2


def test_ignore_rules_unit():
    r = IgnoreRules(["build/", "*.min.js", "a/b/*.txt"])
    assert r.matches("build/x.py") and r.matches("src/app.min.js") and r.matches("a/b/c.txt")
    assert not r.matches("src/app.js")


def test_is_test_path():
    for p in ("tests/a.py", "src/__tests__/a.js", "test_a.py", "a_test.go", "web/a.spec.ts", "x/fixtures/y.txt"):
        assert is_test_path(p)
    for p in ("src/app.py", "latest/a.py", "docs/a.md"):
        assert not is_test_path(p)


def test_staged(tmp_path):
    run = lambda *a: subprocess.run(["git", "-C", str(tmp_path), *a], check=True, capture_output=True)
    run("init", "-q")
    (tmp_path / "staged.py").write_text(LEAK)
    (tmp_path / "unstaged.py").write_text(LEAK)
    run("add", "staged.py")
    found, _ = names(tmp_path, staged=True)
    assert found == {"staged.py"}


def test_cli_exit_codes_and_json(tmp_path, capsys):
    (tmp_path / "a.py").write_text(LEAK)
    assert main(["scan", str(tmp_path), "--no-llm", "--json"]) == 1
    out = json.loads(capsys.readouterr().out)
    assert out["summary"]["reportable"] == 1 and H.aws() not in json.dumps(out)
    clean = tmp_path / "clean"
    clean.mkdir()
    (clean / "b.py").write_text("x = 1\n")
    assert main(["scan", str(clean), "--no-llm"]) == 0


def test_cli_ollama_down_falls_back_loudly(tmp_path, capsys):
    (tmp_path / "a.py").write_text(LEAK)
    assert main(["scan", str(tmp_path), "--host", "http://127.0.0.1:9"]) == 1  # finding still reported
    cap = capsys.readouterr()
    assert "Cannot reach Ollama" in cap.err and "warning:" in cap.err and "WARNING" in cap.out


def test_cli_require_llm_is_strict(tmp_path, capsys):
    (tmp_path / "a.py").write_text(LEAK)
    assert main(["scan", str(tmp_path), "--host", "http://127.0.0.1:9", "--require-llm"]) == 2
    err = capsys.readouterr().err
    assert "Cannot reach Ollama" in err and "--no-llm" in err


def test_cli_missing_path(capsys):
    assert main(["scan", "/definitely/not/here", "--no-llm"]) == 2
