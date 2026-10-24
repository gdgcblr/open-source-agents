from __future__ import annotations

from rce_sentinel.config import Settings
from rce_sentinel.scanner.rules import (
    load_rules,
    parse_python,
    scan_python,
    scan_regex,
    strip_comments,
)


def _py(settings: Settings, src: str, suppress: bool = True):
    rules = load_rules(settings.rule_files, "t")
    mod = parse_python("m.py", src)
    assert mod is not None
    return scan_python(mod, rules.python, suppress)  # type: ignore[arg-type]


def _regex(settings: Settings, path: str, src: str):
    rules = load_rules(settings.rule_files, "t")
    pack = rules.pack_for(path)
    assert pack is not None
    return scan_regex(path, src, pack, True)


def test_alias_import_is_resolved(settings: Settings) -> None:
    found = _py(settings, "from os import system as s\ndef f(x):\n    s(x)\n")
    assert [f.rule_id for f in found] == ["py-os-system"]
    assert found[0].sink == "os.system"


def test_subprocess_only_with_shell_true(settings: Settings) -> None:
    src = ("import subprocess\n"
           "subprocess.run(['ls', x])\n"
           "subprocess.run(cmd, shell=False)\n"
           "subprocess.run(cmd, shell=True)\n")
    found = _py(settings, src)
    assert [(f.rule_id, f.line) for f in found] == [("py-subprocess-shell", 4)]


def test_yaml_safe_loader_not_flagged(settings: Settings) -> None:
    src = ("import yaml\n"
           "yaml.load(d, Loader=yaml.SafeLoader)\n"
           "yaml.load(d, yaml.CSafeLoader)\n"
           "yaml.safe_load(d)\n"
           "yaml.load(d, Loader=yaml.FullLoader)\n")
    found = _py(settings, src)
    assert [f.line for f in found] == [5]


def test_constant_argument_is_marked(settings: Settings) -> None:
    found = _py(settings, "import os\nos.system('df -h')\n")
    assert found[0].arg_kind == "constant"


def test_ssti_method_name_match(settings: Settings) -> None:
    src = "from jinja2 import Environment\nenv = Environment()\nenv.from_string(t)\n"
    assert [f.rule_id for f in _py(settings, src)] == ["py-ssti-jinja"]


def test_inline_suppression_is_reported_not_hidden(settings: Settings) -> None:
    src = "import pickle\npickle.loads(b)  # rce-sentinel: ignore[py-pickle]\n"
    found = _py(settings, src)
    assert found and found[0].suppressed
    assert not _py(settings, src, suppress=False)[0].suppressed


def test_strip_comments_keeps_strings_and_lines() -> None:
    src = "a = '// not a comment'\n// eval(x)\n/* eval(y)\n*/ b = 1\n"
    out = strip_comments(src)
    assert "// not a comment" in out
    assert "eval" not in out
    assert out.count("\n") == src.count("\n")


def test_js_rules(settings: Settings) -> None:
    src = ("const dir = req.query.dir;\n"
           "exec('ls ' + dir);\n"
           "// eval(req.body.code)\n"
           "/a+/.exec('aaa');\n"
           "eval('1+1');\n"
           "eval(req.body.code);\n")
    found = _regex(settings, "s.js", src)
    assert [(f.rule_id, f.line, f.arg_kind) for f in found] == [
        ("js-child-process-exec", 2, "tainted"), ("js-eval", 6, "tainted")]


def test_go_exec_shell(settings: Settings) -> None:
    src = 'cmd := exec.Command("sh", "-c", r.FormValue("q"))\n'
    ids = {f.rule_id for f in _regex(settings, "main.go", src)}
    assert "go-exec-shell" in ids


def test_rule_files_are_pluggable(settings: Settings, tmp_path) -> None:
    extra = tmp_path / "ruby.yaml"
    extra.write_text("language: ruby\nextensions: ['.rb']\nsources: ['params\\[']\nrules:\n"
                     "  - {id: rb-eval, title: eval, cwe: CWE-95, severity: high,\n"
                     "     pattern: '\\beval\\s*\\(', attacker_path: x, fix: y}\n")
    rules = load_rules([*settings.rule_files, extra], "t")
    pack = rules.pack_for("a.rb")
    assert pack is not None
    assert scan_regex("a.rb", "eval(params[:x])\n", pack, True)[0].arg_kind == "tainted"
