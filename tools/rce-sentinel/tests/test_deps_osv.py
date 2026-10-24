from __future__ import annotations

import json

from rce_sentinel.engine import Scanner
from rce_sentinel.models import Dependency
from rce_sentinel.scanner import deps
from rce_sentinel.scanner.osv import is_rce, version_affected


def test_requirements_parser() -> None:
    out = deps.parse_requirements("PyYAML==5.3  # pin\nflask>=2\n-r other.txt\n", "r.txt")
    assert [(d.name, d.version) for d in out] == [("pyyaml", "5.3"), ("flask", None)]


def test_package_lock_parser() -> None:
    text = json.dumps({"packages": {"": {}, "node_modules/lodash": {"version": "4.17.20"}}})
    out = deps.parse_manifest("package-lock.json", text)
    assert [(d.ecosystem, d.name, d.version) for d in out] == [("npm", "lodash", "4.17.20")]


def test_go_sum_and_cargo() -> None:
    gosum = "github.com/a/b v1.2.3 h1:x=\ngithub.com/a/b v1.2.3/go.mod h1:y=\n"
    assert len(deps.parse_manifest("go.sum", gosum)) == 1
    cargo = '[[package]]\nname = "serde"\nversion = "1.0.0"\n'
    assert deps.parse_manifest("Cargo.lock", cargo)[0].ecosystem == "crates.io"


def test_poetry_lock() -> None:
    lock = '[[package]]\nname = "PyYAML"\nversion = "5.3"\n'
    assert deps.parse_manifest("poetry.lock", lock)[0].name == "pyyaml"


def test_diff_deps_only_changed() -> None:
    old = deps.parse_requirements("a==1\nb==1\n", "r.txt")
    new = deps.parse_requirements("a==1\nb==2\nc==1\n", "r.txt")
    assert [(d.name, d.version) for d in deps.diff_deps(old, new)] == [("b", "2"), ("c", "1")]


def test_version_ranges() -> None:
    aff = {"ranges": [{"type": "ECOSYSTEM", "events": [{"introduced": "0"}, {"fixed": "5.4"}]}]}
    assert version_affected(aff, "5.3")
    assert not version_affected(aff, "5.4")
    assert not version_affected(aff, "6.0.1")


def test_rce_filter() -> None:
    assert is_rce(["CWE-502"], "")
    assert is_rce(["CWE-20"], "allows arbitrary code execution via full_load")
    assert not is_rce(["CWE-79"], "reflected XSS in admin page")
    assert not is_rce(["CWE-434"], "upload of large files")
    assert is_rce(["CWE-434"], "upload of a webshell leads to execution")


def test_offline_lookup_from_seed(scanner: Scanner) -> None:
    dep = Dependency(ecosystem="PyPI", name="pyyaml", version="5.3", file="r.txt")
    advs = scanner.osv.lookup([dep])["PyPI|pyyaml|5.3"]
    assert {a.id for a in advs} == {"GHSA-6757-jp84-gxfx", "GHSA-8q59-q68h-6hv4"}
    fixed = {a.id: a.fixed_version for a in advs}
    assert fixed["GHSA-8q59-q68h-6hv4"] == "5.4"
    patched = Dependency(ecosystem="PyPI", name="pyyaml", version="6.0.1", file="r.txt")
    assert scanner.osv.lookup([patched])["PyPI|pyyaml|6.0.1"] == []
