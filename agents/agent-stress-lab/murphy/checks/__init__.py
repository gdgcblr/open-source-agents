"""Build checks from config and run them. Built-ins: trace, python, http; or an import path to a class."""

from __future__ import annotations

from murphy import plugins
from murphy.checks.base import Check, CheckResult, RunContext
from murphy.checks.builtin import HttpCheck, PythonCheck, TraceCheck
from murphy.config.schema import CheckConfig

__all__ = ["Check", "CheckResult", "RunContext", "build_checks", "run_checks"]


def build_check(cfg: CheckConfig) -> Check:
    opts = cfg.extras
    common = {"id": cfg.id, "label": cfg.label, "hint": cfg.hint}
    if cfg.type == "trace":
        return TraceCheck(**common, **opts)
    if cfg.type == "python":
        return PythonCheck(**common, fn=plugins.load(opts["fn"]))
    if cfg.type == "http":
        return HttpCheck(**common, **opts)
    if plugins.is_import_path(cfg.type):
        return plugins.load(cfg.type)(**common, **opts)
    raise ValueError(f"checks[{cfg.id}].type: unknown type {cfg.type!r} (use trace, python, http, or module:Class)")


def build_checks(cfgs: list[CheckConfig]) -> list[Check]:
    return [build_check(c) for c in cfgs]


def run_checks(checks: list[Check], ctx: RunContext) -> list[CheckResult]:
    results = []
    for check in checks:
        try:
            results.append(check.run(ctx))
        except Exception as exc:  # a broken check is a failed check, not a crashed matrix
            results.append(CheckResult(check.id, False, check.label, f"check error: {type(exc).__name__}: {exc}", check.hint))
    return results
