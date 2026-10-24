from __future__ import annotations

from rce_sentinel.config import Settings
from rce_sentinel.scanner import taint
from rce_sentinel.scanner.rules import load_rules, parse_python, scan_python


def _trace(settings: Settings, files: dict[str, str]):
    pack = load_rules(settings.rule_files, "t").python
    assert pack is not None
    mods = [m for p, s in files.items() if (m := parse_python(p, s))]
    findings = [f for m in mods for f in scan_python(m, pack, True)]
    taint.apply_taint(findings, taint.trace(mods, pack), pack)
    return {(f.file, f.line): f for f in findings}


def test_request_param_reaches_sink(settings: Settings) -> None:
    src = ("import os\nfrom flask import request\n"
           "def h():\n    host = request.args.get('h')\n    cmd = 'ping ' + host\n"
           "    os.system(cmd)\n")
    f = _trace(settings, {"a.py": src})[("a.py", 6)]
    assert f.arg_kind == "tainted"
    assert "request.args.get" in f.taint_chain[0]
    assert "request.args.get" in f.attacker_path


def test_route_parameters_are_sources(settings: Settings) -> None:
    src = ("import os\n@app.route('/x/<name>')\ndef h(name):\n    os.system(name)\n")
    assert _trace(settings, {"a.py": src})[("a.py", 4)].arg_kind == "tainted"


def test_plain_function_parameter_is_not_tainted(settings: Settings) -> None:
    src = "import os\ndef h(name):\n    os.system(name)\n"
    assert _trace(settings, {"a.py": src})[("a.py", 3)].arg_kind == "unknown"


def test_sanitizer_stops_taint(settings: Settings) -> None:
    src = ("import os, shlex, sys\ndef h():\n    x = shlex.quote(sys.argv[1])\n"
           "    os.system('ls ' + x)\n")
    assert _trace(settings, {"a.py": src})[("a.py", 4)].arg_kind == "unknown"


def test_cross_file_taint(settings: Settings) -> None:
    files = {
        "views.py": ("from flask import request\nfrom helpers import run\n"
                     "def v():\n    return run(request.args['c'])\n"),
        "helpers.py": "import subprocess\ndef run(c):\n    subprocess.run(c, shell=True)\n",
    }
    f = _trace(settings, files)[("helpers.py", 3)]
    assert f.arg_kind == "tainted"
    assert any("views.py:4" in step for step in f.taint_chain)


def test_env_and_file_read_sources(settings: Settings) -> None:
    src = ("import os, pickle\ndef h():\n    data = open('/tmp/x', 'rb').read()\n"
           "    pickle.loads(data)\n    eval(os.environ['E'])\n")
    found = _trace(settings, {"a.py": src})
    assert found[("a.py", 4)].arg_kind == "tainted"
    assert found[("a.py", 5)].arg_kind == "tainted"
