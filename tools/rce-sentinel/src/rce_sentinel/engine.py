"""Scan pipeline, cheapest layer first:
dependencies (OSV, no LLM) -> rules/AST -> taint -> reachability -> LLM judge (ambiguous only).
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from rce_sentinel import gitio
from rce_sentinel.config import PROMPT_VERSION, Settings
from rce_sentinel.memory.casefile import CaseFile
from rce_sentinel.memory.store import Store
from rce_sentinel.memory.trust import repo_id
from rce_sentinel.models import Advisory, Dependency, Finding, RunStats, ScanReport
from rce_sentinel.netio import SafeClient
from rce_sentinel.orchestrator import prompts as P
from rce_sentinel.orchestrator.budget import Budget
from rce_sentinel.orchestrator.llm import ModelRegistry, Provider, make_provider
from rce_sentinel.orchestrator.router import Router
from rce_sentinel.scanner import deps as depmod
from rce_sentinel.scanner import reachability, risk, taint
from rce_sentinel.scanner.linters import scan_with_linter
from rce_sentinel.scanner.osv import OsvClient, ThreatFeeds
from rce_sentinel.scanner.pyast import stable_hash
from rce_sentinel.scanner.rules import (
    PyModule,
    RuleSet,
    load_rules,
    parse_python,
    scan_python,
)

SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".rce-sentinel", "dist",
             "build", ".tox", ".mypy_cache", ".ruff_cache"}
BASELINE_OUT_TOKENS = 300


@dataclass
class FileSet:
    """Files to scan plus, for diff scans, their old versions and changed lines."""

    contents: dict[str, str]
    changed_lines: dict[str, set[int]] | None = None
    old_contents: dict[str, str] = field(default_factory=dict)
    repo_python: dict[str, str] = field(default_factory=dict)


def collect_staged(repo: Path) -> FileSet:
    contents = {}
    for p in gitio.staged_files(repo):
        if (text := gitio.staged_content(repo, p)) is not None:
            contents[p] = text
    old = {p: t for p in contents if depmod.is_manifest(p)
           and (t := gitio.head_content(repo, p)) is not None}
    repo_py = {}
    for p in gitio.tracked_files(repo):
        if p.endswith(".py") and p not in contents and not _skipped(p) and (
                t := gitio.working_content(repo, p)) is not None:
            repo_py[p] = t
    return FileSet(contents, gitio.staged_changed_lines(repo), old, repo_py)


def collect_tree(repo: Path, use_git: bool = True) -> FileSet:
    contents = {}
    if use_git:
        paths = gitio.tracked_files(repo)
    else:
        paths = [str(p.relative_to(repo)) for p in repo.rglob("*") if p.is_file()]
    for p in paths:
        if _skipped(p):
            continue
        if (t := gitio.working_content(repo, p)) is not None:
            contents[p] = t
    return FileSet(contents)


def _skipped(path: str) -> bool:
    return any(part in SKIP_DIRS for part in Path(path).parts)


class Scanner:
    def __init__(self, settings: Settings, store: Store | None = None,
                 provider: Provider | None = None, registry: ModelRegistry | None = None):
        self.settings = settings
        self.store = store or Store(settings.db_path)
        src = settings.sources
        self.http = SafeClient(src.get("allowed_hosts", []),
                               timeout=float(src.get("request_timeout_seconds", 15)),
                               max_bytes=int(src.get("max_response_bytes", 5_000_000)),
                               user_agent=src.get("user_agent", "rce-sentinel"))
        self.registry = registry or ModelRegistry(settings.models, settings.provider_mode)
        self.provider = provider or make_provider(self.registry)
        overlay = {k: v for k, v in settings.symbols.items() if k != "import_names"}
        self.import_overlay: dict[str, list[str]] = settings.symbols.get("import_names", {})
        self.osv = OsvClient(self.store, None if self.http.offline else self.http, overlay)
        self.feeds = ThreatFeeds(self.store, None if self.http.offline else self.http)
        self.rules: RuleSet = load_rules(settings.rule_files, settings.rules_version)
        self.repo_id = repo_id(settings.repo_root)
        self.emit: Callable[[str], None] = lambda _m: None  # live progress (trace prints it)

    # --- entry point --------------------------------------------------------------
    def scan(self, files: FileSet, mode: str, wall_seconds: float | None = None,
             commit: str = "") -> ScanReport:
        t0 = time.monotonic()
        run_id = uuid.uuid4().hex[:10]
        started = datetime.now(UTC).isoformat(timespec="seconds")
        degraded: list[str] = []
        policy = self.settings.policy
        allow_suppress = bool(policy.get("allow_inline_suppressions", True))

        if shipped := gitio.tracked_under(self.settings.repo_root, ".rce-sentinel"):
            degraded.append(
                f".rce-sentinel/ is tracked by git ({len(shipped)} file(s)): shipped state is "
                "untrusted; cached verdicts and facts are only used if signed with this "
                "machine's key")
        manifests = {p: t for p, t in files.contents.items() if depmod.is_manifest(p)}
        code_files = {p: t for p, t in files.contents.items() if p not in manifests}

        # Parse Python once; reachability also needs unchanged repo files.
        modules = [m for p, t in code_files.items() if p.endswith(".py")
                   if (m := parse_python(p, t))]
        repo_modules = modules + [m for p, t in files.repo_python.items()
                                  if (m := parse_python(p, t))]

        # Layer 1: dependencies (zero LLM calls, ever).
        dep_findings, all_deps = self._dependency_layer(manifests, files, repo_modules)
        if dep_findings:
            self.emit(f"[tools] dependency layer (OSV + reachability): {len(dep_findings)} "
                      f"RCE-class advisory(ies), "
                      f"{sum(1 for f in dep_findings if f.reachable)} reachable")
        if self.osv.online_errors:
            degraded.append("OSV unreachable; used local cache: " + self.osv.online_errors[0])

        # Layers 2-3: rules and taint.
        lint_timeout = max(2.0, (wall_seconds or 60.0) - (time.monotonic() - t0))
        code_findings, lint_notes = self._code_layer(code_files, modules, allow_suppress,
                                                     lint_timeout)
        degraded += lint_notes
        tainted = sum(1 for f in code_findings if f.arg_kind == "tainted")
        self.emit(f"[tools] rules/AST: {len(code_findings)} sink hit(s); taint tracer: "
                  f"{tainted} source-to-sink path(s)")
        for note in lint_notes:
            self.emit(f"  ! {note}")
        if files.changed_lines is not None:
            code_findings = [f for f in code_findings
                             if self._in_diff(f, files.changed_lines, modules)]

        versions = {"rules": self.settings.rules_version, "cve_db": self.osv.db_version(),
                    "prompt": PROMPT_VERSION}

        # Pre-router: only ambiguous or confirmable code findings may reach an LLM.
        needs_llm = [f for f in code_findings if not f.suppressed and f.arg_kind != "constant"]
        prerouted = len(files.contents) - len({f.file for f in needs_llm})
        budget = Budget.from_policy(policy, wall_seconds)
        casefile = CaseFile.build(repo_modules, sorted(p for p in code_files
                                                       if not p.endswith(".py")),
                                  all_deps, code_findings)
        router = Router(self.settings, self.store, self.registry, self.provider, budget,
                        run_id, versions, casefile, self._rules_digest())
        self.last_router = router
        router.emit = self.emit
        self.emit(f"[pre-router] {len(needs_llm)} finding(s) need a model; "
                  f"{len(code_findings) - len(needs_llm)} decided by rules alone (zero tokens)")
        if wall_seconds and time.monotonic() - t0 > wall_seconds:
            degraded.append(f"static layers exceeded {wall_seconds:.0f}s budget; "
                            "LLM judge skipped, rules-only")
            needs_llm = []
        elif needs_llm and not self.registry.any_available():
            degraded.append("no LLM available (no API keys, Ollama not running); rules-only")
            needs_llm = []

        merge_notes = self._judge_all(router, needs_llm, files.contents)
        degraded += router.degraded
        if self.store.rejected_rows:
            degraded.append(f"ignored {self.store.rejected_rows} stored verdict(s)/fact(s) "
                            "with a missing or invalid signature")

        severities = {r.id: r.severity for p in self.rules.packs for r in p.rules}
        for f in code_findings:
            f.risk = risk.score_code(f, severities.get(f.rule_id, "medium"))
        self._realert_code(code_findings)
        self._record_facts(code_findings, versions, commit)

        findings = sorted(dep_findings + code_findings,
                          key=lambda f: (-(f.risk.score if f.risk else 0), f.file, f.line))
        block_on = list(policy.get("block_on", ["critical", "high"]))
        blocked = mode == "pre-commit" and any(risk.blocks(f, block_on) for f in findings)

        stats = RunStats(llm_calls=router.stats.llm_calls, cache_hits=router.stats.cache_hits,
                         units_total=len(files.contents), units_skipped_prerouter=prerouted,
                         units_judged=len(needs_llm),
                         tokens_in=router.stats.tokens_in, tokens_out=router.stats.tokens_out,
                         cost_usd=round(router.stats.cost_usd, 6))
        report = ScanReport(run_id=run_id, mode=mode, started=started,
                            duration_s=round(time.monotonic() - t0, 2), degraded=degraded,
                            findings=findings, blocked=blocked, stats=stats, versions=versions)
        if merge_notes:
            report.versions["merge_notes"] = merge_notes
        self._save_run(report, files)
        return report

    # --- layers ---------------------------------------------------------------------
    def _dependency_layer(self, manifests: dict[str, str], files: FileSet,
                          modules: list[PyModule]) -> tuple[list[Finding], list[Dependency]]:
        all_deps: list[Dependency] = []
        to_check: list[Dependency] = []
        for path, text in manifests.items():
            new = depmod.parse_manifest(path, text)
            all_deps += new
            if files.changed_lines is not None:
                old = depmod.parse_manifest(path, files.old_contents.get(path, ""))
                new = depmod.diff_deps(old, new)
            to_check += new
        results = self.osv.lookup(to_check)
        findings = []
        pack = self.rules.python
        for dep in to_check:
            key = f"{dep.ecosystem}|{dep.name}|{dep.version}"
            advisories = results.get(key, [])
            newly_listed = self._realert_dep(dep, advisories)
            for adv in advisories:
                reach = reachability.check(adv, dep, modules, self.import_overlay, pack)
                cves = adv.cve_ids
                kev = self.feeds.in_kev(cves)
                epss = self.feeds.epss(cves) if cves else None
                score = risk.score_dependency(risk.cvss3_base(adv.cvss_vector), epss, kev,
                                              reach.reachable)
                fix = (f"Upgrade {dep.name} to {adv.fixed_version} or later."
                       if adv.fixed_version else
                       f"No fixed release of {dep.name}; pin, remove, or mitigate.")
                sym = adv.symbols[0] if adv.symbols else "the vulnerable API"
                site = ""
                if reach.reachable:
                    site, sym = reach.evidence[0].split(" ")[:2]
                path = (f"Attacker sends crafted input to {site}, "
                        f"which calls {sym} in {dep.name} {dep.version} ({adv.id}) and "
                        f"executes code." if reach.reachable else
                        f"{dep.name} {dep.version} has {adv.id}; exploitation needs a call "
                        f"to {sym}, which this repo "
                        f"{'may make' if reach.reachable is None else 'does not make'}.")
                findings.append(Finding(
                    id=stable_hash(dep.file, adv.id, dep.name, dep.version or ""),
                    layer="dependency", rule_id=adv.id, title=adv.summary[:120],
                    cwe=",".join(adv.cwes) or "n/a", file=dep.file, line=1,
                    sink=sym, attacker_path=path, fix=fix, dependency=dep, advisory=adv,
                    reachable=reach.reachable, reach_evidence=reach.evidence, risk=score,
                    decided_by="osv+reachability",
                    realert=(f"new intel since last scan: {adv.id} now affects this version"
                             if adv.id in newly_listed else None)))
        return findings, all_deps

    def _code_layer(self, code_files: dict[str, str], modules: list[PyModule],
                    allow_suppress: bool, timeout: float) -> tuple[list[Finding], list[str]]:
        findings: list[Finding] = []
        notes: list[str] = []
        pack = self.rules.python
        if pack:
            for mod in modules:
                findings += scan_python(mod, pack, allow_suppress)
            hits = taint.trace(modules, pack)
            taint.apply_taint(findings, hits, pack)
        by_pack: dict[str, dict[str, str]] = {}
        for path, text in code_files.items():
            rp = self.rules.pack_for(path)
            if rp and rp.language != "python":
                by_pack.setdefault(rp.language, {})[path] = text
        for lang, files in by_pack.items():
            rp = next(p for p in self.rules.packs if p.language == lang)
            found, note = scan_with_linter(rp, files, allow_suppress, timeout)
            findings += found
            if note:
                notes.append(note)
        return findings, notes

    @staticmethod
    def _in_diff(f: Finding, changed: dict[str, set[int]], modules: list[PyModule]) -> bool:
        lines = changed.get(f.file, set())
        if f.line in lines:
            return True
        mod = next((m for m in modules if m.path == f.file), None)
        if mod is None:
            return False
        for start, end, _ in mod.ranges:
            if start <= f.line <= end and any(start <= ln <= end for ln in lines):
                return True
        return False

    def _judge_all(self, router: Router, needs: list[Finding],
                   contents: dict[str, str]) -> str:
        by_file: dict[str, list[Finding]] = {}
        for f in needs:
            by_file.setdefault(f.file, []).append(f)

        def work(path: str) -> None:
            lines = contents[path].splitlines()
            for f in by_file[path]:
                out = router.judge(f, lines)
                f.verdict = out.verdict
                f.trust = out.trust
                f.decided_by = out.decided_by
                f.internal_notes = " | ".join(out.trail)
                if out.notes:
                    f.internal_notes += f" | model: {out.notes}"

        workers = int(self.settings.policy.get("router", {}).get("max_workers", 4))
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            list(pool.map(work, by_file))
        vuln = {p: [f"{f.rule_id} L{f.line}" for f in fs
                    if f.verdict and f.verdict.verdict == "vulnerable"]
                for p, fs in by_file.items()}
        vuln = {p: v for p, v in vuln.items() if v}
        return router.merge(vuln) if len(vuln) >= 2 else ""

    # --- memory -----------------------------------------------------------------
    def _realert_dep(self, dep: Dependency, advisories: list[Advisory]) -> set[str]:
        """Record the dependency verdict; return advisory ids new since the last scan."""
        rows = self.store.execute(
            "SELECT status, advisories FROM dep_verdicts WHERE ecosystem=? AND name=? "
            "AND version=?", (dep.ecosystem, dep.name, dep.version or ""))
        ids = sorted(a.id for a in advisories)
        prev_ids = set(json.loads(rows[0]["advisories"])) if rows else None
        self.store.execute(
            "INSERT OR REPLACE INTO dep_verdicts VALUES (?,?,?,?,?,?,?)",
            (dep.ecosystem, dep.name, dep.version or "", "vulnerable" if ids else "clean",
             json.dumps(ids), self.osv.db_version(), time.time()))
        return set() if prev_ids is None else set(ids) - prev_ids

    def _realert_code(self, findings: list[Finding]) -> None:
        for f in findings:
            if f.verdict is None or f.verdict.verdict != "vulnerable":
                continue
            prior = self.store.prior_facts(f.file, f.sink, repo_id=self.repo_id, limit=1)
            if prior and prior[0]["verdict"] == "safe":
                f.realert = (f"previously judged safe by {prior[0]['model_used']} at "
                             f"{prior[0]['commit_sha']}; now vulnerable")

    def _record_facts(self, findings: list[Finding], versions: dict[str, str],
                      commit: str) -> None:
        for f in findings:
            if f.verdict is None or f.decided_by.startswith("cache"):
                continue
            reason = f.verdict.exploit_path or f.verdict.suggested_fix or f.decided_by
            self.store.add_fact({
                "context_hash": f.context_hash, "file": f.file, "sink": f.sink,
                "rule_id": f.rule_id, "finding_json": f.model_dump_json(exclude={"verdict"}),
                "verdict": f.verdict.verdict, "reason": reason,
                "evidence_json": json.dumps([e.model_dump() for e in f.verdict.evidence]),
                "model_used": f.decided_by, "rules_version": versions["rules"],
                "cve_db_version": versions["cve_db"], "commit_sha": commit or "working-tree",
                "invalidated_by": None, "created_at": time.time()},
                repo_id=self.repo_id, trust=f.trust)

    def _rules_digest(self) -> str:
        return ", ".join(sorted(r.id for p in self.rules.packs for r in p.rules))

    def _save_run(self, report: ScanReport, files: FileSet) -> None:
        baseline = self.registry.baseline()
        system = P.system_prompt(P.JUDGE_SYSTEM, False, self._rules_digest())
        out_tok = self._avg_plain_out_tokens()
        b_tokens_in = sum(P.approx_tokens(system + t[:24000]) for t in files.contents.values())
        b_tokens_out = out_tok * len(files.contents)
        b_cost = baseline.cost(b_tokens_in, b_tokens_out)
        s = report.stats
        self.store.execute(
            "INSERT OR REPLACE INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (report.run_id, report.mode, time.time(), report.duration_s,
             json.dumps(report.degraded), len(report.findings), int(report.blocked),
             s.units_total, s.cache_hits, s.units_skipped_prerouter, len(files.contents),
             b_tokens_in + b_tokens_out, b_cost, s.units_judged))

    def _avg_plain_out_tokens(self) -> int:
        row = self.store.execute(
            "SELECT AVG(tokens_out) AS a FROM llm_calls WHERE caveman=0 AND task_type='judge'")
        return int(row[0]["a"] or BASELINE_OUT_TOKENS)
