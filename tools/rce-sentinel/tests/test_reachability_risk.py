from __future__ import annotations

from rce_sentinel.config import Settings
from rce_sentinel.models import Advisory, Dependency, Finding, Verdict
from rce_sentinel.scanner import reachability, risk
from rce_sentinel.scanner.rules import load_rules, parse_python

YAML_ADV = Advisory(id="GHSA-8q59-q68h-6hv4", symbols=["yaml.load", "yaml.full_load"])
YAML_DEP = Dependency(ecosystem="PyPI", name="pyyaml", version="5.3", file="r.txt")


def _reach(settings: Settings, src: str, adv: Advisory = YAML_ADV,
           dep: Dependency = YAML_DEP) -> reachability.Reach:
    pack = load_rules(settings.rule_files, "t").python
    mod = parse_python("a.py", src)
    assert mod is not None
    return reachability.check(adv, dep, [mod], {"pyyaml": ["yaml"], "pillow": ["PIL"]}, pack)


def test_reachable_call(settings: Settings) -> None:
    r = _reach(settings, "import yaml\nyaml.load(d, Loader=yaml.FullLoader)\n")
    assert r.reachable is True
    assert r.evidence[0].startswith("a.py:2")


def test_safe_loader_call_is_not_reachable(settings: Settings) -> None:
    r = _reach(settings, "import yaml\nyaml.load(d, Loader=yaml.SafeLoader)\n")
    assert r.reachable is False
    assert "safe arguments" in r.evidence[0]


def test_imported_but_not_called(settings: Settings) -> None:
    adv = Advisory(id="GHSA-3f63-hfp8-52jq", symbols=["PIL.ImageMath.eval"])
    dep = Dependency(ecosystem="PyPI", name="pillow", version="10.0.0", file="r.txt")
    r = _reach(settings, "from PIL import Image\nImage.open(p)\n", adv, dep)
    assert r.reachable is False and r.imported


def test_alias_reaches_symbol(settings: Settings) -> None:
    adv = Advisory(id="X", symbols=["PIL.ImageMath.eval"])
    dep = Dependency(ecosystem="PyPI", name="pillow", version="10.0.0", file="r.txt")
    r = _reach(settings, "from PIL import ImageMath as M\nM.eval(e)\n", adv, dep)
    assert r.reachable is True


def test_cvss3_base_scores() -> None:
    assert risk.cvss3_base("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H") == 9.8
    assert risk.cvss3_base("CVSS:3.1/AV:N/AC:H/PR:N/UI:N/S:U/C:H/I:H/A:H") == 8.1
    assert risk.cvss3_base("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H") == 10.0
    assert risk.cvss3_base("CVSS:3.1/AV:L/AC:L/PR:L/UI:N/S:U/C:N/I:N/A:N") == 0.0
    assert risk.cvss3_base("garbage") is None


def test_dependency_score_reachability_and_kev() -> None:
    reach = risk.score_dependency(9.8, 0.06, False, True)
    unreach = risk.score_dependency(9.8, 0.06, False, False)
    unknown = risk.score_dependency(9.8, 0.06, False, None)
    kev = risk.score_dependency(7.0, None, True, True)
    assert reach.label == "critical"
    assert unreach.score < 4 and unreach.label == "low"
    assert unreach.score < unknown.score < reach.score
    assert kev.score >= 9.5


def test_code_score() -> None:
    f = Finding(id="1", layer="taint", rule_id="r", title="t", cwe="CWE-78", file="a",
                line=1, arg_kind="tainted")
    assert risk.score_code(f, "high").label == "critical"
    f.arg_kind = "constant"
    assert risk.score_code(f, "high").label == "low"
    f.arg_kind = "unknown"
    f.verdict = Verdict(verdict="safe", confidence=0.95)
    assert risk.score_code(f, "high").score <= 3.0
    f.risk = risk.score_code(f, "high")
    assert not risk.blocks(f, ["critical", "high"])
