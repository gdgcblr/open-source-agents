"""Zero-day intel agent loop.

poll collectors -> dedupe -> triage (rules first, tier-1 LLM only if unclear) -> match the
repo SBOM -> reachability + risk -> response plan, checked by a cross-family verifier ->
draft patch + advisory note + webhook. Never commits, pushes, or merges.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from functools import partial
from typing import Any

from pydantic import BaseModel

from rce_sentinel.engine import Scanner, collect_tree
from rce_sentinel.intel import mitigation, notify
from rce_sentinel.intel.base import Collector
from rce_sentinel.intel.collectors.darkweb_stub import DarkWebStub
from rce_sentinel.intel.collectors.feeds import CisaKev, Ghsa, Nvd, OsvTargeted
from rce_sentinel.intel.collectors.rss import RssCollector
from rce_sentinel.intel.collectors.social import Bluesky, Mastodon, XTwitter
from rce_sentinel.memory.casefile import CaseFile
from rce_sentinel.memory.trust import SINGLE, UNVERIFIED
from rce_sentinel.models import Advisory, Dependency, IntelItem
from rce_sentinel.orchestrator import prompts as P
from rce_sentinel.orchestrator.a2a import A2AError
from rce_sentinel.orchestrator.budget import Budget
from rce_sentinel.orchestrator.router import Router, VerifyOut
from rce_sentinel.scanner import deps as depmod
from rce_sentinel.scanner import reachability, risk
from rce_sentinel.scanner.osv import is_rce
from rce_sentinel.scanner.rules import parse_python

MIN_NAME_LEN = 4


class TriageOut(BaseModel):
    rce: bool
    confidence: float
    packages: list[dict[str, str]] = []
    reason: str = ""


class PlanOut(BaseModel):
    steps: list[str] = []
    waf_hint: str = ""
    notes: str = ""


@dataclass
class IntelResult:
    fetched: int = 0
    new: int = 0
    rce: int = 0
    matched: int = 0
    proposals: list[str] = field(default_factory=list)
    realerts: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    notified: list[str] = field(default_factory=list)
    notices: list[str] = field(default_factory=list)


class IntelAgent:
    def __init__(self, scanner: Scanner):
        self.scanner = scanner
        self.repo_id = scanner.repo_id
        self.settings = scanner.settings
        self.store = scanner.store
        files = collect_tree(self.settings.repo_root, use_git=_is_git(self.settings.repo_root))
        self.contents = files.contents
        self.inventory: list[Dependency] = [
            d for p, t in files.contents.items() if depmod.is_manifest(p)
            for d in depmod.parse_manifest(p, t)]
        self.modules = [m for p, t in files.contents.items() if p.endswith(".py")
                        if (m := parse_python(p, t))]

    def collectors(self) -> list[Collector]:
        cfg = self.settings.sources.get("collectors", {})
        http = self.scanner.http
        built: list[Collector] = [
            CisaKev(cfg.get("cisa_kev", {}), http), Nvd(cfg.get("nvd", {}), http),
            OsvTargeted(cfg.get("osv", {}), http), Ghsa(cfg.get("ghsa", {}), http),
            Mastodon(cfg.get("mastodon", {}), http), Bluesky(cfg.get("bluesky", {}), http),
            XTwitter(cfg.get("x_twitter", {}), http), DarkWebStub(cfg.get("darkweb", {}), http),
        ]
        for name in ("oss_security", "exploitdb", "project_zero", "vendor_rss"):
            built.append(RssCollector(name, cfg.get(name, {}), http))
        return [c for c in built if c.enabled()]

    # --- loop ---------------------------------------------------------------------
    def run_once(self, simulated: list[IntelItem] | None = None) -> IntelResult:
        res = IntelResult()
        items: list[IntelItem] = list(simulated or [])
        if simulated is None:
            for c in self.collectors():
                try:
                    items += c.fetch(self.inventory)
                except Exception as exc:  # one bad feed must not stop the others
                    res.errors.append(f"{c.name}: {type(exc).__name__}: {str(exc)[:80]}")
        res.fetched = len(items)
        router = self._router()
        for item in self._dedupe(items):
            res.new += 1
            if not self._triage(item, router):
                self._mark(item, "not-rce")
                continue
            res.rce += 1
            matches = self._match(item)
            if not matches:
                self._mark(item, "no-match")
                continue
            res.matched += 1
            for dep in matches:
                self._respond(item, dep, router, res, simulated is not None)
            self._mark(item, "matched")
        res.notices = list(router.degraded)
        return res

    def _router(self) -> Router:
        versions = {"rules": self.settings.rules_version,
                    "cve_db": self.scanner.osv.db_version(), "prompt": P.PROMPT_VERSION}
        budget = Budget.from_policy(self.settings.policy)
        casefile = CaseFile.build(self.modules, [], self.inventory, [])
        return Router(self.settings, self.store, self.scanner.registry, self.scanner.provider,
                      budget, "intel-" + str(int(time.time())), versions, casefile, "")

    def _dedupe(self, items: list[IntelItem]) -> list[IntelItem]:
        out, seen = [], set()
        for it in items:
            keys = [it.content_hash, it.url, *it.cve_ids]
            if any(k in seen for k in keys if k):
                continue
            rows = self.store.execute(
                "SELECT 1 FROM intel_items WHERE content_hash=? OR url=?",
                (it.content_hash, it.url))
            cve_rows = [self.store.execute(
                "SELECT 1 FROM intel_items WHERE cve_ids LIKE ? AND status='matched'",
                (f'%"{c}"%',)) for c in it.cve_ids]
            if rows or any(cve_rows):
                continue
            seen.update(k for k in keys if k)
            out.append(it)
        return out

    def _mark(self, item: IntelItem, status: str) -> None:
        self.store.execute("INSERT OR REPLACE INTO intel_items VALUES (?,?,?,?,?,?,?)",
                           (item.content_hash, item.source, item.url, json.dumps(item.cve_ids),
                            item.model_dump_json(), status, time.time()))

    # --- steps ----------------------------------------------------------------------
    def _triage(self, item: IntelItem, router: Router) -> bool:
        text = f"{item.title} {item.summary}"
        if is_rce(item.cwes, text):
            return True
        if item.cwes or not self._match(item):
            return False  # zero tokens: known non-RCE CWE, or nothing in our inventory
        if router.pick("tier1") is None:
            return False
        system = P.system_prompt(P.TRIAGE_SYSTEM, router.caveman)
        try:
            text = router.bus.relay("collector:feed", "triage:tier1", "intel_item",
                                    f"{item.title}\n{item.summary}", UNVERIFIED)
        except A2AError:
            return False
        user = "TASK: triage\n" + P.untrusted("intel", text, 2000)
        out, _, _, _ = router.ask_fb(partial(router.pick, "tier1"), "triage", system, user,
                                     TriageOut, max_tokens=200)
        return bool(out and out.rce and out.confidence >= router.threshold)

    def _match(self, item: IntelItem) -> list[Dependency]:
        named = {(p.get("ecosystem"), p.get("name", "").lower()) for p in item.packages}
        names = {n for _, n in named}
        text = f"{item.title} {item.summary}".lower()
        out = []
        for d in self.inventory:
            listed = (d.ecosystem, d.name) in named or d.name in names
            mentioned = len(d.name) >= MIN_NAME_LEN and re.search(
                rf"\b{re.escape(d.name)}\b", text)
            if listed or mentioned:
                out.append(d)
        return out

    def _advisory_for(self, item: IntelItem, dep: Dependency) -> Advisory | None:
        advs = self.scanner.osv.lookup([dep]).get(f"{dep.ecosystem}|{dep.name}|{dep.version}", [])
        for a in advs:
            if set(a.cve_ids) & set(item.cve_ids) or a.id in item.title:
                return a
        return None

    def _respond(self, item: IntelItem, dep: Dependency, router: Router, res: IntelResult,
                 simulated: bool) -> None:
        if item.kev and item.confirmed:
            for cve in item.cve_ids:
                self.scanner.feeds.add_kev({"cveID": cve, "source": item.source,
                                            "catalogVersion": "simulated" if simulated
                                            else "intel"}, simulated=simulated)
        adv = self._advisory_for(item, dep)
        probe = adv or Advisory(id=(item.cve_ids or [item.content_hash])[0],
                                aliases=item.cve_ids, summary=item.summary)
        overlay = {k: v for k, v in self.settings.symbols.items() if k != "import_names"}
        if not probe.symbols:
            probe.symbols = sorted({s for k in [probe.id, *probe.aliases]
                                    for s in overlay.get(k, [])})
        reach = reachability.check(probe, dep, self.modules,
                                   self.settings.symbols.get("import_names", {}),
                                   self.scanner.rules.python)
        cves = probe.cve_ids
        epss = self.scanner.feeds.epss(cves) if cves else None
        score = risk.score_dependency(risk.cvss3_base(probe.cvss_vector), epss,
                                      bool(item.kev and item.confirmed), reach.reachable)
        if not item.confirmed:
            score.factors["unconfirmed"] = True
        steps, verifier_note = self._plan(item, dep, probe, reach, router)
        proposal = mitigation.build(self.settings.repo_root, dep, adv, reach, item, score,
                                    verifier_note, steps)
        out = mitigation.write(proposal, self.settings.state_dir / "proposals")
        res.proposals.append(str(out))
        if item.confirmed:  # rumours never rewrite earlier verdicts
            res.realerts += self._realert(dep, probe, item)
        msg = (f"rce-sentinel: {proposal.title} | {score.label} {score.score} | "
               f"reachable={reach.reachable} | {item.url} | draft in {out}")
        res.notified += notify.notify(self.scanner.http, msg)

    def _plan(self, item: IntelItem, dep: Dependency, adv: Advisory,
              reach: reachability.Reach, router: Router) -> tuple[list[str], str]:
        """Tier-2 drafts plan steps; a different-family model checks the claim."""
        lab = router.registry.label
        if router.pick("tier2") is None:
            return [], "no LLM available; deterministic plan only"
        facts = (f"PACKAGE: {dep.ecosystem} {dep.name} {dep.version}\n"
                 f"ADVISORY: {adv.id} fixed={adv.fixed_version}\n"
                 f"REACHABLE: {reach.reachable} {reach.evidence[:2]}")
        try:
            text = router.bus.relay("collector:feed", "planner:tier2", "intel_item",
                                    f"{item.title}\n{item.summary}", UNVERIFIED)
        except A2AError as exc:
            return [], f"a2a rejected the intel item: {exc}"
        intel = P.untrusted("intel", text, 2000)
        system = P.system_prompt(P.PLAN_SYSTEM, router.caveman)
        plan, _, err, spec = router.ask_fb(
            partial(router.pick, "tier2"), "plan", system, f"TASK: plan\n{facts}\n{intel}",
            PlanOut, max_tokens=300)
        if plan is None or spec is None:
            return [], f"plan model failed ({err})"
        verifier = router.pick_verifier(spec)
        if verifier is None:
            return plan.steps, f"plan by {lab(spec)}; no cross-family verifier available"
        vsys = P.system_prompt(P.VERIFY_SYSTEM, router.caveman)
        try:
            claim = router.bus.relay(
                "planner:tier2", "verifier:for-plan", "verify_request",
                f"{dep.name} {dep.version} affected by {', '.join(item.cve_ids) or adv.id}; "
                f"plan={plan.steps}", SINGLE)
        except A2AError as exc:
            return plan.steps, f"a2a rejected the verify request: {exc}"
        vuser = f"TASK: verify\n{P.untrusted('claim', claim, 1500)}\n{facts}\n{intel}"
        check, _, _, verifier = router.ask_fb(
            partial(router.pick_verifier, spec), "verify", vsys, vuser, VerifyOut,
            max_tokens=150)
        if check is None or verifier is None:
            return plan.steps, f"plan by {lab(spec)}; verifier {lab(verifier)} gave no answer"
        verdict = "agreed" if check.agree else "DISAGREED"
        return plan.steps, (f"plan by {lab(spec)}; {lab(verifier)} ({verifier.family}) "
                            f"{verdict}")

    def _realert(self, dep: Dependency, adv: Advisory, item: IntelItem) -> list[str]:
        """Invalidate cached 'safe' facts on affected symbols and say so."""
        out = []
        for sym in adv.symbols:
            rows = self.store.execute(
                "SELECT id, file, sink, verdict FROM facts WHERE sink=? AND verdict='safe' "
                "AND repo_id=? AND invalidated_by IS NULL", (sym, self.repo_id))
            for r in rows:
                self.store.execute("UPDATE facts SET invalidated_by=? WHERE id=?",
                                   (item.content_hash, r["id"]))
                out.append(f"{r['file']} {r['sink']}: earlier 'safe' verdict invalidated by "
                           f"{', '.join(item.cve_ids) or item.url}")
        prev = self.store.execute(
            "SELECT status FROM dep_verdicts WHERE ecosystem=? AND name=? AND version=?",
            (dep.ecosystem, dep.name, dep.version or ""))
        if prev and prev[0]["status"] == "clean":
            out.append(f"{dep.name} {dep.version}: previously clean, now affected by "
                       f"{', '.join(item.cve_ids) or adv.id}")
        return out


def _is_git(path: Any) -> bool:
    return (path / ".git").exists()


def load_simulated(path: str) -> list[IntelItem]:
    from pathlib import Path

    from rce_sentinel.intel.base import make_item

    data = json.loads(Path(path).read_text())
    items = []
    for d in data if isinstance(data, list) else [data]:
        items.append(make_item(d.get("source", "simulated"), d["url"], d["title"],
                               d.get("summary", ""), float(d.get("credibility", 1.0)),
                               confirmed=bool(d.get("confirmed", True)),
                               cwes=d.get("cwes", []), packages=d.get("packages", []),
                               published=d.get("published", ""), kev=bool(d.get("kev"))))
    return items
