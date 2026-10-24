import sys

from dead_code_reaper.analyzer import scan
from dead_code_reaper.verifier import keep_closure, verify

PYTEST = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"]


def statuses(result):
    return {r.key: r.status for r in result.removals}


def test_dead_code_verified_and_dynamic_use_needed(make_project):
    root = make_project({
        "pkg/__init__.py": "",
        "pkg/core.py": """
            def dead():
                return 0

            def used_by_name():
                return 1

            def call(name):
                return globals()[name]()
        """,
        "tests/test_core.py": """
            from pkg.core import call

            def test_call():
                name = "used" + "_by_name"
                assert call(name) == 1
        """,
    })
    s = scan(root)
    result = verify(s, test_cmd=PYTEST, log=lambda m: None)
    st = statuses(result)
    assert st["pkg/core.py::dead"] == "verified"
    assert st["pkg/core.py::used_by_name"] == "needed"
    assert "pkg/core.py" in result.final_files


def test_no_tests_falls_back_to_import_check(make_project):
    root = make_project({"pkg/__init__.py": "", "pkg/a.py": "def dead():\n    pass\n"})
    result = verify(scan(root), log=lambda m: None)
    assert result.check_mode == "import"
    assert statuses(result)["pkg/a.py"] == "unverified"  # the unused module


def test_failing_baseline_removes_nothing(make_project):
    root = make_project({
        "mod.py": "def dead():\n    pass\n",
        "tests/test_x.py": "def test_fail():\n    assert False\n",
    })
    result = verify(scan(root), test_cmd=PYTEST, log=lambda m: None)
    assert not result.baseline_passed
    assert result.final_files == {}


def test_run_cap_marks_rest_unverified(make_project):
    root = make_project({
        "mod.py": "def a():\n    pass\n\n\ndef b():\n    pass\n",
        "tests/test_x.py": "def test_ok():\n    pass\n",
    })
    result = verify(scan(root), test_cmd=PYTEST, max_runs=1, log=lambda m: None)
    assert set(statuses(result).values()) == {"unverified"}


def test_keep_closure_follows_used_by(make_project):
    root = make_project({"mod.py": "def old():\n    return _h()\n\n\ndef _h():\n    pass\n"})
    s = scan(root)
    kept, why = keep_closure(s.removals, {"mod.py::old"})
    assert "mod.py::_h" in kept and why["mod.py::_h"] == "mod.py::old"


def test_copy_is_imported_not_an_installed_original(make_project, monkeypatch):
    # Simulate an editable install: the original project is on PYTHONPATH.
    root = make_project({
        "src/pkg/__init__.py": "",
        "src/pkg/core.py": "def dead():\n    return 0\n\n\ndef used():\n    return 1\n",
        "tests/test_core.py": "from pkg.core import used\n\n\ndef test_used():\n    assert used() == 1\n",
    })
    monkeypatch.setenv("PYTHONPATH", str(root / "src"))
    result = verify(scan(root), test_cmd=PYTEST, log=lambda m: None)
    assert result.baseline_passed
    assert statuses(result)["src/pkg/core.py::dead"] == "verified"
