"""End-to-end checks for the acceptance criteria, all offline with the mock provider."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from rce_sentinel import cli
from rce_sentinel.config import load_settings
from rce_sentinel.costreport import gather, render
from rce_sentinel.engine import Scanner, collect_staged, collect_tree
from rce_sentinel.intel.agent import IntelAgent, load_simulated
from rce_sentinel.memory.store import Store
from rce_sentinel.memory.trust import VERIFIED, repo_id
from rce_sentinel.orchestrator.llm import MockProvider, ModelRegistry
from rce_sentinel.report import markdown

from .conftest import FIXTURES, TOOL_ROOT, git, seed_osv

SVC = 'import os\n\n\ndef handler():\n    user_input = input("host: ")\n    os.system(user_input)\n'


def _scanner(repo: Path, mode: str = "mock") -> tuple[Scanner, MockProvider]:
    settings = load_settings(repo)
    provider = MockProvider()
    sc = Scanner(settings, store=Store(settings.db_path), provider=provider,
                 registry=ModelRegistry(settings.models, mode))
    seed_osv(sc)
    return sc, provider


def test_precommit_blocks_os_system_user_input(git_repo: Path) -> None:
    (git_repo / "svc.py").write_text(SVC)
    git(git_repo, "add", "svc.py")
    sc, _ = _scanner(git_repo)
    rep = sc.scan(collect_staged(git_repo), "pre-commit", wall_seconds=10)
    assert rep.blocked
    top = rep.findings[0]
    assert (top.file, top.rule_id, top.risk.label) == ("svc.py", "py-os-system", "critical")
    assert "\n" not in top.attacker_path and "input('host: ')" in top.attacker_path
    assert cli.main(["--repo", str(git_repo), "scan", "--staged"]) == 1


def test_lockfile_only_diff_makes_zero_llm_calls(git_repo: Path) -> None:
    req = git_repo / "requirements.txt"
    req.write_text(req.read_text() + "Jinja2==3.1.4\n")
    git(git_repo, "add", "requirements.txt")
    sc, provider = _scanner(git_repo)
    rep = sc.scan(collect_staged(git_repo), "pre-commit", wall_seconds=10)
    assert rep.stats.llm_calls == 0 and provider.calls == []
    assert not rep.blocked


def test_repeat_scan_is_all_cache_hits(repo: Path) -> None:
    sc, provider = _scanner(repo)
    first = sc.scan(collect_tree(repo, use_git=False), "full")
    assert first.stats.llm_calls > 0
    provider.calls.clear()
    second = sc.scan(collect_tree(repo, use_git=False), "full")
    assert second.stats.llm_calls == 0 and provider.calls == []
    assert second.stats.cache_hits == first.stats.units_judged


def test_model_swap_keeps_scan_cache(repo: Path, tmp_path: Path,
                                     monkeypatch: pytest.MonkeyPatch) -> None:
    sc, _ = _scanner(repo)
    sc.scan(collect_tree(repo, use_git=False), "full")
    cfg = tmp_path / "cfg"
    import shutil

    shutil.copytree(TOOL_ROOT / "config", cfg)
    text = (cfg / "models.yaml").read_text().replace("id: apple-foundationmodel",
                                                     'id: "qwen3:8b"', 1)
    (cfg / "models.yaml").write_text(text)
    monkeypatch.setenv("RCE_SENTINEL_CONFIG_DIR", str(cfg))
    sc2, _provider = _scanner(repo)
    assert sc2.registry.all["tier1"][0].id == "qwen3:8b"
    rep = sc2.scan(collect_tree(repo, use_git=False), "full")
    assert rep.stats.llm_calls == 0 and rep.stats.cache_hits > 0


def test_no_api_keys_degraded_mode_still_blocks(git_repo: Path) -> None:
    (git_repo / "svc.py").write_text(SVC)
    git(git_repo, "add", "svc.py")
    sc, provider = _scanner(git_repo, mode="auto")  # no keys set, Ollama not running
    sc.registry._local_up = {"apfel": set(), "ollama": set()}
    rep = sc.scan(collect_staged(git_repo), "pre-commit", wall_seconds=10)
    assert rep.blocked and provider.calls == []
    assert any("rules-only" in d for d in rep.degraded)


def test_time_budget_degrades_to_rules_only(repo: Path) -> None:
    sc, provider = _scanner(repo)
    rep = sc.scan(collect_tree(repo, use_git=False), "full", wall_seconds=1e-9)
    assert provider.calls == []
    assert any("budget" in d for d in rep.degraded)


def test_unreachable_dependency_is_low(repo: Path) -> None:
    sc, _ = _scanner(repo)
    rep = sc.scan(collect_tree(repo, use_git=False), "full")
    pillow = [f for f in rep.findings if f.dependency and f.dependency.name == "pillow"]
    pyyaml = [f for f in rep.findings if f.dependency and f.dependency.name == "pyyaml"]
    assert pillow and all(f.risk.label == "low" and f.reachable is False for f in pillow)
    assert pyyaml and all(f.reachable and f.risk.label == "critical" for f in pyyaml)


def test_new_intel_realerts_previously_clean_dependency(repo: Path) -> None:
    settings = load_settings(repo)
    sc = Scanner(settings, store=Store(settings.db_path), provider=MockProvider(),
                 registry=ModelRegistry(settings.models, "mock"))
    first = sc.scan(collect_tree(repo, use_git=False), "full")  # empty OSV cache
    assert not [f for f in first.findings if f.dependency]
    seed_osv(sc)  # feed changes
    second = sc.scan(collect_tree(repo, use_git=False), "full")
    deps = [f for f in second.findings if f.dependency]
    assert deps and all(f.realert for f in deps)


def test_simulated_kev_produces_draft_never_a_push(git_repo: Path) -> None:
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest()
              for p in git_repo.rglob("*") if p.is_file() and ".git" not in p.parts}
    head = git(git_repo, "rev-parse", "HEAD")
    sc, _ = _scanner(git_repo)
    sc.store.add_fact({"context_hash": "x", "file": "app.py", "sink": "yaml.load",
                       "rule_id": "py-yaml-load", "verdict": "safe", "reason": "old review",
                       "model_used": "tier1:m", "commit_sha": "abc"},
                      repo_id=repo_id(git_repo), trust=VERIFIED)
    agent = IntelAgent(sc)
    res = agent.run_once(load_simulated(str(TOOL_ROOT / "demo" / "simulated_kev.json")))
    assert res.matched == 2
    kev_dir = Path(res.proposals[0])
    patch = (kev_dir / "mitigation.patch").read_text()
    assert "+PyYAML==5.4" in patch and "yaml.safe_load(request.data)" in patch
    assert "did not commit, push, or open a PR" in (kev_dir / "PR_DRAFT.md").read_text()
    assert any("invalidated" in r for r in res.realerts)
    assert git(git_repo, "rev-parse", "HEAD") == head
    after = {p: hashlib.sha256(p.read_bytes()).hexdigest()
             for p in git_repo.rglob("*") if p.is_file() and ".git" not in p.parts
             and ".rce-sentinel" not in p.parts}
    assert after == {p: h for p, h in before.items() if ".rce-sentinel" not in p.parts}
    stored = " ".join(r["json"] for r in sc.store.execute("SELECT json FROM intel_items"))
    assert "os.system" not in stored and "evil.example" not in stored
    social = next(p for p in res.proposals if "requests" in p)
    assert "UNCONFIRMED" in (Path(social) / "ADVISORY.md").read_text()
    assert not sc.feeds.in_kev(["CVE-2026-0000"])


def test_social_only_item_never_blocks(git_repo: Path) -> None:
    sc, _ = _scanner(git_repo)
    IntelAgent(sc).run_once(load_simulated(str(TOOL_ROOT / "demo" / "simulated_kev.json")))
    req = git_repo / "requirements.txt"
    req.write_text(req.read_text().replace("requests==2.32.3", "requests==2.32.4"))
    git(git_repo, "add", "requirements.txt")
    rep = sc.scan(collect_staged(git_repo), "pre-commit", wall_seconds=10)
    assert not rep.blocked


def test_caveman_internal_only_and_measured(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RCE_SENTINEL_CAVEMAN_PROBE", "1")
    sc, _ = _scanner(repo)
    rep = sc.scan(collect_tree(repo, use_git=False), "full")
    data = gather(sc.store, sc.registry)
    assert data["caveman_pairs"] > 0
    assert data["caveman_out_on"] < data["caveman_out_off"]
    md = markdown(rep)
    assert "CAVEMAN" not in md and " L16." not in md
    os_sys = next(f for f in rep.findings if f.rule_id == "py-os-system" and f.line == 16)
    assert os_sys.attacker_path.startswith("Attacker controls")


def test_caveman_off_flag(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CAVEMAN", "off")
    assert load_settings(repo).caveman is False
    monkeypatch.setenv("CAVEMAN", "on")
    assert load_settings(repo).caveman is True


def test_cost_report_beats_baseline(repo: Path) -> None:
    sc, _ = _scanner(repo)
    sc.scan(collect_tree(repo, use_git=False), "full")
    sc.scan(collect_tree(repo, use_git=False), "full")
    data = gather(sc.store, sc.registry)
    assert 0 <= data["actual_usd"] < data["baseline_usd"]
    assert data["result_cache_hits"] > 0
    assert "savings:" in render(data)


def test_report_files_written(repo: Path) -> None:
    assert cli.main(["--repo", str(repo), "osv-import", str(FIXTURES / "osv_seed.json")]) == 0
    assert cli.main(["--repo", str(repo), "scan"]) == 0
    state = load_settings(repo).state_dir
    data = json.loads((state / "report.json").read_text())
    assert data["findings"] and (state / "report.md").read_text().startswith("# rce-sentinel")
