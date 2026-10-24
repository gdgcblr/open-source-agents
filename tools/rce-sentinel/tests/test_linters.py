from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from rce_sentinel.config import Settings
from rce_sentinel.scanner.linters import EslintBackend, GosecBackend, scan_with_linter
from rce_sentinel.scanner.rules import load_rules

from .conftest import FIXTURES

needs_eslint = pytest.mark.skipif(not EslintBackend().available(),
                                  reason="node or linters/eslint/node_modules missing")


def _pack(settings: Settings, lang: str):
    return next(p for p in load_rules(settings.rule_files, "t").packs if p.language == lang)


@needs_eslint
def test_eslint_backend_on_fixture(settings: Settings) -> None:
    src = (FIXTURES / "vuln_repo" / "web" / "server.js").read_text()
    found, note = scan_with_linter(_pack(settings, "javascript"), {"web/server.js": src},
                                   True, 30)
    assert note is None
    got = {(f.rule_id, f.line, f.arg_kind) for f in found}
    assert got == {("js-child-process-exec", 7, "tainted"), ("js-eval", 12, "tainted")}
    exec_hit = next(f for f in found if f.rule_id == "js-child-process-exec")
    assert exec_hit.scope == (5, 8) and "req.query.dir" in exec_hit.attacker_path


@needs_eslint
def test_eslint_ast_taint_and_typescript(settings: Settings) -> None:
    src = ('import { execSync } from "node:child_process";\n'
           "import * as cp from 'child_process';\n"
           "const { cmd } = req.query;\n"
           'execSync("ls");\n'
           "cp.exec(`git log ${cmd}`);\n"
           "execSync('echo ' + Number(req.query.n));\n"
           "const m = require(process.argv[2] as string);\n"
           "/a+/.exec('aaa');\n")
    found, _ = scan_with_linter(_pack(settings, "javascript"), {"a.ts": src}, True, 30)
    got = {(f.rule_id, f.line, f.arg_kind) for f in found}
    assert ("js-child-process-exec", 5, "tainted") in got
    assert ("js-dynamic-require", 7, "tainted") in got
    assert not any(line in {4, 8} for _, line, _ in got)
    assert ("js-child-process-exec", 6, "tainted") not in got  # Number() sanitises


@needs_eslint
def test_scanned_repo_cannot_disable_rules_or_load_config(settings: Settings) -> None:
    files = {
        "eslint.config.js": "throw new Error('repo config must never load');\n",
        "x.js": "// eslint-disable-next-line\neval(req.body.code);\n",
    }
    found, note = scan_with_linter(_pack(settings, "javascript"), files, True, 30)
    assert note is None
    assert [(f.file, f.rule_id) for f in found] == [("x.js", "js-eval")]


def test_missing_eslint_falls_back_to_regex(settings: Settings, tmp_path: Path,
                                            monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RCE_SENTINEL_ESLINT_DIR", str(tmp_path / "nope"))
    src = "const d = req.query.d;\nexec('ls ' + d);\n"
    found, note = scan_with_linter(_pack(settings, "javascript"), {"a.js": src}, True, 30)
    assert note and "regex fallback" in note
    assert [f.rule_id for f in found] == ["js-child-process-exec"]


def test_gosec_output_mapping(settings: Settings) -> None:
    files = {"main.go": ('package main\nimport "os/exec"\nfunc h(q string) {\n'
                         '\texec.Command("sh", "-c", q).Run()\n\texec.Command(q).Run()\n}\n')}
    tmp = Path("/tmp/rce-sentinel-lint-x").resolve()
    data = {"Issues": [
        {"rule_id": "G204", "file": str(tmp / "main.go"), "line": "4"},
        {"rule_id": "G204", "file": str(tmp / "main.go"), "line": "5"},
        {"rule_id": "G104", "file": str(tmp / "main.go"), "line": "4"},
    ]}
    found = GosecBackend().parse(data, tmp, files, _pack(settings, "go"), True)
    assert [(f.rule_id, f.line) for f in found] == [("go-exec-shell", 4),
                                                    ("go-exec-variable", 5)]


@pytest.mark.skipif(shutil.which("gosec") is not None, reason="gosec installed")
def test_go_without_gosec_uses_regex(settings: Settings) -> None:
    src = 'cmd := exec.Command("sh", "-c", r.FormValue("q"))\n'
    found, note = scan_with_linter(_pack(settings, "go"), {"m.go": src}, True, 30)
    assert note and "gosec not installed" in note
    assert "go-exec-shell" in {f.rule_id for f in found}


@needs_eslint
def test_full_scan_uses_eslint_not_fallback(scanner) -> None:
    from rce_sentinel.engine import collect_tree

    rep = scanner.scan(collect_tree(scanner.settings.repo_root, use_git=False), "full")
    assert not any("eslint" in d for d in rep.degraded), rep.degraded
    js = [f for f in rep.findings if f.file.endswith(".js")]
    assert js and all(f.scope for f in js)  # scope ranges only come from the ESLint plugin
