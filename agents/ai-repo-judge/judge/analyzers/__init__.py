"""Static analyzers. Each takes a Workspace and returns checks, findings and facts for one dimension."""

from __future__ import annotations

from judge.analyzers import ai_native, compliance, docs, quality, reproducibility, security
from judge.models import AnalyzerResult
from judge.workspace import Workspace


def run_all(ws: Workspace, *, online: bool = True) -> dict[str, AnalyzerResult]:
    return {
        "compliance": compliance.analyze(ws),
        "security": security.analyze(ws, online=online),
        "quality": quality.analyze(ws),
        "functionality": reproducibility.analyze(ws),
        "ai_native": ai_native.analyze(ws),
        "docs": docs.analyze(ws),
    }
