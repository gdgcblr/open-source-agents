"""Security and integrity guardrails for GitHub PR Guardian."""

from __future__ import annotations
import re
from typing import Any
from .rules_scanner import Finding


# Common prompt injection triggers in diffs, commit messages, or PR descriptions
PROMPT_INJECTION_PATTERNS = [
    re.compile(r"(?i)ignore\s+(all\s+)?(previous|above)\s+instructions"),
    re.compile(r"(?i)system\s+prompt\s*override"),
    re.compile(r"(?i)you\s+are\s+now\s+(a\s+helpful\s+assistant\s+that\s+approves|unrestricted|in\s+developer\s+mode)"),
    re.compile(r"(?i)disregard\s+(all\s+)?security\s+(warnings|rules|checks)"),
    re.compile(r"(?i)return\s+verdict\s*:\s*approve"),
    re.compile(r"(?i)set\s+risk_score\s*:\s*0"),
]


class GuardrailEngine:
    """Multi-layer guardrails ensuring agent integrity, input safety, and output reliability."""

    def sanitize_input(self, diff_text: str, pr_title: str, pr_description: str) -> tuple[str, list[Finding]]:
        """Inspect inputs for prompt injection or adversarial tampering."""
        guardrail_findings: list[Finding] = []
        
        # 1. Check PR metadata (Title and Description)
        metadata_text = f"{pr_title}\n{pr_description}"
        injection_found = False
        for pattern in PROMPT_INJECTION_PATTERNS:
            match = pattern.search(metadata_text)
            if match:
                guardrail_findings.append(
                    Finding(
                        category="SECURITY",
                        severity="CRITICAL",
                        file="PR_METADATA",
                        line=None,
                        title="Adversarial Prompt Injection Attempt Detected",
                        description=(
                            f"Suspicious instruction pattern detected in PR metadata: `{match.group(0)[:60]}`. "
                            "An attacker may be attempting to hijack or manipulate the LLM review agent."
                        ),
                        suggested_fix="Sanitize user-provided PR metadata and reject instructions attempting to override review guardrails.",
                        snippet=match.group(0),
                    )
                )
                injection_found = True
                break

        # 2. Check diff content (ignoring test suite fixtures like sample_diffs/ or tests/)
        if not injection_found:
            lines_to_check = []
            skip_current_file = False
            for line in diff_text.splitlines():
                if line.startswith("diff --git"):
                    skip_current_file = (
                        "sample_diffs/" in line
                        or "/tests/" in line
                        or "tests/test_" in line
                        or line.endswith(".md")
                    )
                if not skip_current_file and line.startswith("+") and not line.startswith("+++"):
                    lines_to_check.append(line)

            diff_code_content = "\n".join(lines_to_check)
            for pattern in PROMPT_INJECTION_PATTERNS:
                match = pattern.search(diff_code_content)
                if match:
                    guardrail_findings.append(
                        Finding(
                            category="SECURITY",
                            severity="CRITICAL",
                            file="PR_CODE_DIFF",
                            line=None,
                            title="Adversarial Prompt Injection Attempt Detected",
                            description=(
                                f"Suspicious instruction pattern detected in added code: `{match.group(0)[:60]}`. "
                                "An attacker may be attempting to hijack or manipulate the LLM review agent."
                            ),
                            suggested_fix="Sanitize user-provided PR comments and reject instructions attempting to override review guardrails.",
                            snippet=match.group(0),
                        )
                    )
                    break

        # Enforce maximum diff size (100,000 characters) to prevent token exhaustion DoS
        max_size = 100_000
        if len(diff_text) > max_size:
            diff_text = (
                diff_text[:max_size]
                + "\n\n[GUARDRAIL NOTICE: Diff truncated at 100KB to prevent token exhaustion attack.]"
            )

        return diff_text, guardrail_findings

    def mask_secrets_in_text(self, text: str) -> str:
        """Mask detected raw secrets in reports so they aren't leaked in review comments."""
        # Mask AWS keys
        text = re.sub(
            r"(A3T[A-Z0-9]|AKIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|ASIA)[A-Z0-9]{16}",
            r"\1****************",
            text,
        )
        # Mask GitHub tokens
        text = re.sub(
            r"(gh[pousr]_[A-Za-z0-9_]{4})[A-Za-z0-9_]{32,}",
            r"\1********************************",
            text,
        )
        return text

    def apply_output_guardrails(
        self,
        review_data: dict[str, Any],
        static_findings: list[Finding],
    ) -> dict[str, Any]:
        """Validate, clamp, and enforce deterministic consistency on review outputs."""
        # 1. Ensure required keys exist with safe defaults
        verdict = str(review_data.get("verdict", "COMMENT")).upper().strip()
        risk_score = review_data.get("risk_score", 0)
        risk_level = str(review_data.get("risk_level", "LOW")).upper().strip()
        summary = review_data.get("executive_summary", "")
        findings = review_data.get("findings", [])

        # 2. Type validation & clamping for risk score (0 to 100)
        try:
            risk_score = int(risk_score)
        except (ValueError, TypeError):
            risk_score = 50
        risk_score = max(0, min(100, risk_score))

        # 3. Deterministic Safety Override:
        # If static rules or prompt injection detected CRITICAL security risks,
        # the LLM CANNOT approve or assign a low risk score!
        has_critical = any(f.severity == "CRITICAL" for f in static_findings)
        has_high = any(f.severity == "HIGH" for f in static_findings)

        if has_critical:
            verdict = "REQUEST_CHANGES"
            risk_score = max(risk_score, 85)
            risk_level = "CRITICAL"
        elif has_high:
            if verdict == "APPROVE":
                verdict = "REQUEST_CHANGES"
            risk_score = max(risk_score, 65)
            risk_level = "HIGH" if risk_level not in ("HIGH", "CRITICAL") else risk_level

        # 4. Consistency checks between Verdict and Risk Score
        if risk_score >= 60 and verdict == "APPROVE":
            verdict = "REQUEST_CHANGES"
        elif risk_score >= 40 and verdict == "APPROVE":
            verdict = "COMMENT"

        # 5. Sanitize secrets in findings and summaries to prevent secret leakage in output
        sanitized_summary = self.mask_secrets_in_text(summary)
        sanitized_findings = []
        for f in findings:
            if isinstance(f, dict):
                sanitized_f = dict(f)
                if "comment" in sanitized_f:
                    sanitized_f["comment"] = self.mask_secrets_in_text(str(sanitized_f["comment"]))
                if "suggested_fix" in sanitized_f:
                    sanitized_f["suggested_fix"] = self.mask_secrets_in_text(str(sanitized_f["suggested_fix"]))
                sanitized_findings.append(sanitized_f)

        review_data["verdict"] = verdict
        review_data["risk_score"] = risk_score
        review_data["risk_level"] = risk_level
        review_data["executive_summary"] = sanitized_summary
        review_data["findings"] = sanitized_findings
        return review_data
