"""Risk score: CVSS base, EPSS, CISA KEV membership, and reachability in one 0-10 number."""

from __future__ import annotations

import math

from rce_sentinel.models import Finding, Label, RiskScore

_W = {
    "AV": {"N": 0.85, "A": 0.62, "L": 0.55, "P": 0.2},
    "AC": {"L": 0.77, "H": 0.44},
    "UI": {"N": 0.85, "R": 0.62},
    "C": {"H": 0.56, "L": 0.22, "N": 0.0},
}
_PR = {"U": {"N": 0.85, "L": 0.62, "H": 0.27}, "C": {"N": 0.85, "L": 0.68, "H": 0.5}}


def _roundup(x: float) -> float:
    i = round(x * 100000)
    return i / 100000.0 if i % 10000 == 0 else (math.floor(i / 10000) + 1) / 10.0


def cvss3_base(vector: str | None) -> float | None:
    """CVSS v3.x base score from a vector string (FIRST specification formula)."""
    if not vector or not vector.startswith("CVSS:3"):
        return None
    try:
        m = dict(p.split(":") for p in vector.split("/")[1:])
        scope = m["S"]
        iss = 1 - (1 - _W["C"][m["C"]]) * (1 - _W["C"][m["I"]]) * (1 - _W["C"][m["A"]])
        changed = 7.52 * (iss - 0.029) - 3.25 * (iss - 0.02) ** 15
        impact = 6.42 * iss if scope == "U" else changed
        expl = 8.22 * _W["AV"][m["AV"]] * _W["AC"][m["AC"]] * _PR[scope][m["PR"]]
        expl *= _W["UI"][m["UI"]]
    except (KeyError, ValueError):
        return None
    if impact <= 0:
        return 0.0
    raw = impact + expl if scope == "U" else 1.08 * (impact + expl)
    return _roundup(min(raw, 10))


def label_for(score: float) -> Label:
    if score >= 9.0:
        return "critical"
    if score >= 7.0:
        return "high"
    if score >= 4.0:
        return "medium"
    return "low"


REACH_FACTOR = {True: 1.0, None: 0.7, False: 0.3}
CODE_BASE = {"tainted": 9.0, "unknown": 6.0, "constant": 2.0}
SEVERITY_ADJ = {"high": 0.0, "medium": -1.0, "low": -2.0}


def score_dependency(cvss: float | None, epss: float | None, kev: bool,
                     reachable: bool | None) -> RiskScore:
    base = cvss if cvss is not None else 7.5
    score = base + 1.5 * (epss or 0.0) + (1.5 if kev else 0.0)
    score *= REACH_FACTOR[reachable]
    if kev and reachable:
        score = max(score, 9.5)
    if reachable is False:
        score = min(score, 3.9)  # unreachable never blocks
    score = round(min(score, 10.0), 1)
    return RiskScore(score=score, label=label_for(score), factors={
        "cvss": cvss, "epss": epss, "kev": kev, "reachable": reachable})


def score_code(f: Finding, severity: str) -> RiskScore:
    score = CODE_BASE[f.arg_kind] + SEVERITY_ADJ.get(severity, 0.0)
    if f.verdict is not None:
        v = f.verdict
        if v.verdict == "vulnerable":
            score = max(score, 7.0 + 2.5 * v.confidence)
        elif v.verdict == "safe":
            score = min(score, 3.0)
    score = round(max(0.0, min(score, 10.0)), 1)
    return RiskScore(score=score, label=label_for(score), factors={
        "arg": f.arg_kind, "severity": severity,
        "verdict": f.verdict.verdict if f.verdict else None})


def blocks(f: Finding, block_on: list[str]) -> bool:
    return bool(f.risk and not f.suppressed and f.risk.label in block_on)
