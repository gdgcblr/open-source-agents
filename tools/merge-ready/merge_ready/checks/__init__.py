"""Check registry and orchestration for MergeReady."""

from __future__ import annotations

from typing import Any, Callable

from merge_ready.checks.agent_safety import check_a01, check_a02, check_a03
from merge_ready.checks.deps import check_r01
from merge_ready.checks.env_drift import check_e01, check_e02
from merge_ready.checks.layout import check_f01, check_l01, check_l02
from merge_ready.checks.scope import check_i01, check_p01
from merge_ready.checks.secrets import check_s01, check_s02, redact_secret
from merge_ready.checks.template import check_d01, check_d02, check_r02
from merge_ready.model import Finding, RuleResult, Severity, ValidationReport, Verdict
from merge_ready.project import ProjectContext

# Explicit classification of required vs. conditional/optional checks
REQUIRED_RULES: frozenset[str] = frozenset({
    "L01",
    "L02",
    "F01",
    "D01",
    "D02",
    "S01",
    "S02",
    "E01",
    "R01",
    "R02",
    "A01",
    "A02",
})

OPTIONAL_RULES: frozenset[str] = frozenset({
    "P01",  # Conditional on git base reference (--base <ref>)
    "I01",  # Conditional on git base reference and repository root
    "E02",  # N/A if no paid model provider SDK is imported
    "A03",  # N/A if no high-impact shell/subprocess capabilities are detected
})

CHECK_REGISTRY: list[tuple[str, Callable[[ProjectContext, dict[str, Any]], RuleResult]]] = [
    ("L01", check_l01),
    ("L02", check_l02),
    ("F01", check_f01),
    ("D01", check_d01),
    ("D02", check_d02),
    ("S01", check_s01),
    ("S02", check_s02),
    ("P01", check_p01),
    ("I01", check_i01),
    ("E01", check_e01),
    ("E02", check_e02),
    ("R01", check_r01),
    ("R02", check_r02),
    ("A01", check_a01),
    ("A02", check_a02),
    ("A03", check_a03),
]


def run_all_checks(ctx: ProjectContext) -> ValidationReport:
    """Execute all registered checks against the given project context deterministically."""
    report = ValidationReport(
        project_path=str(ctx.project_path),
        category=ctx.category,
        slug=ctx.slug,
        base_ref=ctx.base_ref,
    )

    # 1. Catch configuration loading / parsing errors
    if getattr(ctx, "config_errors", None):
        for err in ctx.config_errors:
            report.execution_errors.append(err)
            safe_err = redact_secret(err)
            report.add_result(
                RuleResult(
                    rule_id="F01",
                    name="Configuration Integrity",
                    verdict=Verdict.ERROR,
                    reason=f"Configuration error: {safe_err}",
                    findings=[
                        Finding(
                            rule_id="F01",
                            severity=Severity.ERROR,
                            message=f"Configuration error: {safe_err}",
                            fix="Fix syntax or schema errors in rules.toml.",
                            source_rule="rules.toml",
                        )
                    ],
                )
            )

    # 2. Execute each check rule safely
    for rule_id, check_fn in CHECK_REGISTRY:
        config = ctx.rules_config.get(rule_id, {})
        try:
            result = check_fn(ctx, config)
        except Exception as e:
            safe_err = redact_secret(str(e))
            diag = f"Validator error during check '{rule_id}': {safe_err}"
            report.execution_errors.append(diag)
            error_finding = Finding(
                rule_id=rule_id,
                severity=Severity.ERROR,
                message=diag,
                fix="Inspect validator implementation or project files causing check crash.",
                source_rule=config.get("source_rule", "MergeReady Runtime"),
            )
            report.add_result(
                RuleResult(
                    rule_id=rule_id,
                    name=config.get("name", rule_id),
                    verdict=Verdict.ERROR,
                    reason=diag,
                    findings=[error_finding],
                )
            )
            continue

        # 3. Guard against malformed rule output (non-RuleResult or invalid verdict)
        if not isinstance(result, RuleResult):
            diag = f"Rule '{rule_id}' returned invalid type '{type(result).__name__}' (expected RuleResult)."
            report.execution_errors.append(diag)
            report.add_result(
                RuleResult(
                    rule_id=rule_id,
                    name=config.get("name", rule_id),
                    verdict=Verdict.ERROR,
                    reason=diag,
                    findings=[
                        Finding(
                            rule_id=rule_id,
                            severity=Severity.ERROR,
                            message=diag,
                            fix="Ensure check function returns a valid RuleResult instance.",
                            source_rule=config.get("source_rule", "MergeReady Runtime"),
                        )
                    ],
                )
            )
            continue

        if not isinstance(result.verdict, Verdict):
            try:
                result.verdict = Verdict(result.verdict)
            except Exception:
                diag = f"Rule '{rule_id}' returned unrecognized verdict '{result.verdict}'."
                report.execution_errors.append(diag)
                result.verdict = Verdict.ERROR
                result.findings.append(
                    Finding(
                        rule_id=rule_id,
                        severity=Severity.ERROR,
                        message=diag,
                        source_rule=config.get("source_rule", "MergeReady Runtime"),
                    )
                )

        # 4. Enforce required rules: required checks cannot be SKIPPED or N/A
        if rule_id in REQUIRED_RULES and result.verdict in (Verdict.SKIP, Verdict.NA):
            diag = f"Required check '{rule_id}' was marked {result.verdict.value}. Required rules cannot be skipped or bypassed."
            report.execution_errors.append(diag)
            result.verdict = Verdict.ERROR
            result.reason = diag
            result.findings.append(
                Finding(
                    rule_id=rule_id,
                    severity=Severity.ERROR,
                    message=diag,
                    fix=f"Check '{rule_id}' is mandatory and must evaluate to PASS, WARN, or FAIL.",
                    source_rule=config.get("source_rule", "MergeReady Policy"),
                )
            )
        elif result.verdict in (Verdict.SKIP, Verdict.NA) and not (result.reason and result.reason.strip()):
            diag = f"Check '{rule_id}' was marked {result.verdict.value} without an explicit documented reason."
            report.execution_errors.append(diag)
            result.verdict = Verdict.ERROR
            result.reason = diag
            result.findings.append(
                Finding(
                    rule_id=rule_id,
                    severity=Severity.ERROR,
                    message=diag,
                    fix="Provide an explicit justification in reason for skipped or non-applicable checks.",
                    source_rule=config.get("source_rule", "MergeReady Policy"),
                )
            )

        report.add_result(result)

    # 5. Guard against missing or omitted required checks
    missing_required = REQUIRED_RULES - set(report.results.keys())
    if missing_required:
        for m_rule in sorted(missing_required):
            diag = f"Required check '{m_rule}' was never executed."
            report.execution_errors.append(diag)
            report.add_result(
                RuleResult(
                    rule_id=m_rule,
                    name=f"Rule {m_rule}",
                    verdict=Verdict.ERROR,
                    reason=diag,
                    findings=[
                        Finding(
                            rule_id=m_rule,
                            severity=Severity.ERROR,
                            message=diag,
                            source_rule="MergeReady Policy",
                            fix=f"Ensure required rule '{m_rule}' is registered and executed.",
                        )
                    ],
                )
            )

    return report
