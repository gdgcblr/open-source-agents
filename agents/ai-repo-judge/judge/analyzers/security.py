"""Security & privacy: secrets (current tree and full PR history), credential files, dangerous code,
AI-specific risks, dependency hygiene and attempts to manipulate AI judges."""

from __future__ import annotations

from judge.analyzers import codesafety, integrity, manifest, secrets
from judge.analyzers import deps as osv
from judge.models import AnalyzerResult, Check, Finding
from judge.workspace import Workspace

DIM = "security"
AI_TITLES = ("Model output", "Agent loop", "LLM API called from browser")


def _code_checks(risky: list[Finding]) -> list[Check]:
    highs = sum(f.severity in ("high", "critical") for f in risky)
    meds = sum(f.severity == "medium" for f in risky)
    ai = [f for f in risky if f.title.startswith(AI_TITLES)]
    return [
        Check(
            id="risky_code",
            dimension=DIM,
            label="No dangerous calls (eval/exec, shell=True, unsafe deserialisation…)",
            weight=3,
            status="fail" if highs else "warn" if meds else "pass",
            score=max(0.0, 1 - 0.35 * highs - 0.15 * meds),
            detail=f"{highs} high, {meds} medium, {len(risky) - highs - meds} low" if risky else "None found",
        ),
        Check(
            id="ai_safety",
            dimension=DIM,
            label="AI-specific safety (model output → exec, unbounded loops, keys in browser)",
            weight=2,
            status="fail" if any(f.severity == "high" for f in ai) else "warn" if ai else "pass",
            detail=f"{len(ai)} issue(s)" if ai else "No AI-specific risks detected",
        ),
    ]


def _vulnerability_findings(vulns: dict) -> list[Finding]:
    return [
        Finding(
            dimension=DIM,
            severity="medium",
            file=dep.file,
            line=dep.line,
            title=f"{dep.name} {dep.exact_version} has {len(ids)} known vulnerabilit{'y' if len(ids) == 1 else 'ies'}",
            detail=", ".join(ids[:5]),
            snippet=" ".join(f"https://osv.dev/vulnerability/{i}" for i in ids[:3]),
            fix=f"Upgrade {dep.name} to a patched release.",
        )
        for dep, ids in vulns.items()
    ]


def _dependency_checks(ws: Workspace, online: bool) -> tuple[list[Finding], list[Check]]:
    deps = manifest.parse(ws).deps
    if not deps:
        return [], []
    pinned = sum(d.pinned for d in deps)
    ratio = pinned / len(deps)
    unpinned = [d.name for d in deps if not d.pinned]
    checks = [
        Check(
            id="deps_pinned",
            dimension=DIM,
            label="Dependencies have version constraints",
            weight=1,
            status="pass" if ratio >= 0.8 else "warn" if ratio >= 0.4 else "fail",
            score=ratio,
            detail=f"{pinned}/{len(deps)} constrained" + (f"; unpinned: {', '.join(unpinned[:6])}" if unpinned else ""),
            fix="Pin versions (e.g. `httpx>=0.27,<1`) so installs are reproducible." if ratio < 0.8 else None,
        )
    ]
    vulns = osv.known_vulnerabilities(deps) if online else None
    exact = sum(1 for d in deps if d.exact_version)
    if vulns is None:
        status, detail = "skip", "OSV lookup skipped (offline)"
    elif vulns:
        status, detail = "fail", f"{len(vulns)} vulnerable package(s) (OSV.dev)"
    else:
        status = "pass" if exact else "skip"
        detail = f"{exact} exact pin(s) checked against OSV.dev" if exact else "No exact pins to check"
    checks.append(Check(id="deps_vulns", dimension=DIM, label="No known-vulnerable dependency versions", weight=2,
                        status=status, detail=detail))  # type: ignore[arg-type]  # fmt: skip
    return _vulnerability_findings(vulns or {}), checks


def analyze(ws: Workspace, *, online: bool = True) -> AnalyzerResult:
    r = AnalyzerResult()

    found, checks = secrets.scan(ws)
    r.findings += found
    r.checks += checks

    found, check = secrets.credential_files(ws)
    r.findings += found
    r.checks.append(check)

    risky = codesafety.python_risks(ws) + codesafety.js_risks(ws)
    r.findings += risky
    r.checks += _code_checks(risky)

    found, checks = _dependency_checks(ws, online)
    r.findings += found
    r.checks += checks

    found, strong, weak = integrity.scan(ws)
    r.findings += found
    r.checks.append(
        Check(
            id="no_manipulation",
            dimension=DIM,
            label="No hidden text or instructions aimed at AI judges",
            weight=2,
            status="fail" if strong else "warn" if weak else "pass",
            detail=f"{strong} directed at graders, {weak} to review" if strong or weak else "None found",
        )
    )
    r.facts["manipulation_lines"] = strong
    return r
