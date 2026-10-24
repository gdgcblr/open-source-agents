from dead_code_reaper.analyzer import guess_mode, scan


def keys(result):
    return {r.key for r in result.removals}


def test_unused_function_and_cascade(make_project):
    root = make_project({
        "pkg/__init__.py": "",
        "pkg/core.py": """
            def used():
                return 1

            def old():
                return _helper()

            def _helper():
                return 2
        """,
        "app.py": "from pkg.core import used\nprint(used())\n",
    })
    r = scan(root)
    assert "pkg/core.py::old" in keys(r)
    assert "pkg/core.py::_helper" in keys(r)
    assert "pkg/core.py::used" not in keys(r)
    helper = r.removal("pkg/core.py::_helper")
    assert helper.used_by == ["pkg/core.py::old"]
    assert "only used by other dead code" in helper.reasons


def test_protections(make_project):
    root = make_project({
        "mod.py": """
            import json

            REGISTRY = {}

            def register(fn):
                REGISTRY[fn.__name__] = fn
                return fn

            @register
            def plugin():
                pass

            class Encoder(json.JSONEncoder):
                def default(self, o):
                    return str(o)

            def by_string():
                pass

            CALLBACK = "by_string"

            def __getattr__(name):
                return name

            def entry():
                pass
        """,
        "setup.cfg": "[options.entry_points]\nconsole_scripts = x = mod:entry\n",
    })
    r = scan(root)
    reasons = dict(r.protected)
    assert "decorated with @register" in reasons["mod.py::plugin"]
    assert "json.JSONEncoder" in reasons["mod.py::Encoder.default"]
    assert "string" in reasons["mod.py::by_string"]
    assert "dunder" in reasons["mod.py::__getattr__"]
    assert "setup.cfg" in reasons["mod.py::entry"]
    assert not any(k.startswith("mod.py::plugin") for k in keys(r))


def test_unused_imports_partial_and_protected(make_project):
    root = make_project({
        "mod.py": """
            from __future__ import annotations
            import os
            from typing import Dict, List
            try:
                import yaml
            except ImportError:
                yaml = None
            import sys  # noqa: F401

            def f(x: List[int]) -> int:
                return len(x)

            print(f([1]))
        """,
    })
    r = scan(root)
    names = {x.name for x in r.removals if x.kind == "import"}
    assert names == {"import os", "from typing import Dict"}
    reasons = dict(r.protected)
    assert any("try" in v for v in reasons.values())
    assert any("noqa" in v for v in reasons.values())


def test_unreachable_and_variables(make_project):
    root = make_project({
        "mod.py": """
            def f(x):
                label = "unused"
                result = compute(x)
                if x:
                    return 1
                    print("never")
                while False:
                    pass
                return 2

            def compute(x):
                return x
        """,
    })
    r = scan(root)
    kinds = sorted((x.kind, x.start) for x in r.removals)
    assert ("variable", 2) in kinds           # pure value, never read
    assert not any(k == "variable" and s == 3 for k, s in kinds)  # call may have side effects
    assert ("unreachable", 6) in kinds
    assert ("unreachable", 7) in kinds


def test_unused_module_and_test_only(make_project):
    root = make_project({
        "pkg/__init__.py": "",
        "app.py": "from pkg import helpers\nhelpers.run()\n",
        "pkg/helpers.py": "def run():\n    pass\n\ndef only_tested():\n    pass\n",
        "pkg/orphan.py": "def thing():\n    pass\n",
        "pkg/script.py": "if __name__ == '__main__':\n    print('hi')\n",
        "tests/test_x.py": "from pkg.helpers import only_tested\n\ndef test_it():\n    only_tested()\n",
    })
    r = scan(root)
    assert "pkg/orphan.py" in keys(r)
    assert "pkg/orphan.py::thing" not in keys(r)        # deleted with its module
    assert "pkg/script.py" not in keys(r)               # run directly
    assert "pkg/helpers.py" not in keys(r)              # imported by app.py
    assert "app.py" not in keys(r)                      # top-level script
    assert [t.key for t in r.test_only] == ["pkg/helpers.py::only_tested"]


def test_library_mode_keeps_public_names(make_project):
    files = {
        "lib/__init__.py": "from .api import public_fn\n",
        "lib/api.py": "def public_fn():\n    pass\n\ndef _private():\n    pass\n",
    }
    app = scan(make_project(files), mode="app")
    assert "lib/api.py::public_fn" not in keys(app)  # re-exported in __init__
    lib = scan(make_project(files), mode="library")
    assert "lib/api.py::_private" in keys(lib)
    assert "lib/__init__.py::import public_fn@1" not in keys(lib)


def test_dynamic_prefix_lowers_confidence(make_project):
    root = make_project({
        "mod.py": """
            def run(kind):
                return globals()["handle_" + kind]()

            def handle_a():
                return 1
        """,
    })
    r = scan(root)
    assert r.removal("mod.py::handle_a").confidence < 50


def test_guess_mode(make_project):
    assert guess_mode(make_project({"pyproject.toml": "[project]\nclassifiers = []\n"}))[0] == "library"
    assert guess_mode(make_project({"main.py": ""}))[0] == "app"
