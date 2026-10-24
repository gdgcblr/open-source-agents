"""Deterministic Prompt Template Linter and Smell Detector."""

import re
from typing import Any, Dict, List, Optional, Set, Tuple
from .models import LintIssue, LintReport, LintSeverity


INJECTION_PATTERNS = [
    (r"(?i)\bignore\s+(all\s+)?(previous|prior)\s+(instructions|prompts|rules)", "Prompt Injection Smell: Direct instruction override attempt."),
    (r"(?i)\bdisregard\s+(all\s+)?(prior|previous)\s+directives", "Prompt Injection Smell: Directive circumvention pattern."),
    (r"(?i)\bsystem\s+override\s*:", "Prompt Injection Smell: Simulated system level privilege escalation."),
    (r"(?i)\byou\s+are\s+now\s+in\s+(developer|god|dan)\s+mode", "Prompt Injection Smell: Jailbreak / persona hijack pattern."),
]

COMMON_TAGS = ["system", "context", "user", "assistant", "instructions", "rules", "examples"]


def estimate_tokens(text: str) -> int:
    """Fast deterministic heuristic token estimation (~4 characters per token)."""
    if not text:
        return 0
    # Average across whitespace words and character length
    words = len(text.split())
    chars = len(text)
    return max(1, int(chars / 3.8))


class PromptLinter:
    """Validates prompt templates, parses variables, and catches semantic prompt smells."""

    def __init__(self, strict_mode: bool = False):
        self.strict_mode = strict_mode

    def extract_variables(self, template_str: str) -> Set[str]:
        """Finds all {variable_name} placeholder patterns in the template (ignoring {{escaped}})."""
        # Replace {{ with dummy to avoid false positives
        cleaned = re.sub(r"\{\{.*?\}\}", "", template_str)
        matches = re.findall(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}", cleaned)
        return set(matches)

    def lint(
        self,
        template_str: str,
        variables: Optional[Dict[str, Any]] = None,
        template_name: str = "prompt_template",
    ) -> LintReport:
        """Performs comprehensive static linting on a prompt template.

        Args:
            template_str: Raw template string with optional {var} placeholders.
            variables: Optional runtime variables supplied for interpolation.
            template_name: Descriptive label for the template.

        Returns:
            LintReport containing all findings, counts, and token estimates.
        """
        variables = variables or {}
        issues: List[LintIssue] = []
        lines = template_str.splitlines()

        # 1. Check for unclosed braces
        escaped_braces = template_str.replace("{{", "").replace("}}", "")
        # Find single unclosed {
        for idx, line in enumerate(lines, 1):
            cleaned_line = line.replace("{{", "").replace("}}", "")
            # Check unmatched single braces
            open_count = cleaned_line.count("{")
            close_count = cleaned_line.count("}")
            if open_count != close_count:
                issues.append(
                    LintIssue(
                        rule_id="UNBALANCED_BRACE",
                        message=f"Line has unmatched braces ({open_count} open vs {close_count} close).",
                        line_number=idx,
                        severity=LintSeverity.ERROR,
                        suggestion="Escape literal braces using '{{' and '}}' or ensure placeholder is closed.",
                    )
                )

        # 2. Variable analysis
        vars_found = sorted(list(self.extract_variables(template_str)))
        supplied_vars = set(variables.keys())
        missing_vars = sorted([v for v in vars_found if v not in supplied_vars])
        unused_vars = sorted([v for v in supplied_vars if v not in vars_found])

        if missing_vars:
            for v in missing_vars:
                issues.append(
                    LintIssue(
                        rule_id="MISSING_VARIABLE",
                        message=f"Placeholder '{{{v}}}' is missing from provided variables.",
                        severity=LintSeverity.ERROR if self.strict_mode else LintSeverity.WARNING,
                        suggestion=f"Supply a value for '{v}' in the variables payload.",
                    )
                )

        if unused_vars:
            for v in unused_vars:
                issues.append(
                    LintIssue(
                        rule_id="UNUSED_VARIABLE",
                        message=f"Variable '{v}' supplied in variables payload is never used in template.",
                        severity=LintSeverity.INFO,
                        suggestion=f"Remove '{v}' from the variables dictionary if not needed.",
                    )
                )

        # 3. Markdown code block audit
        fence_count = len(re.findall(r"^```", template_str, re.MULTILINE))
        if fence_count % 2 != 0:
            issues.append(
                LintIssue(
                    rule_id="UNCLOSED_CODE_BLOCK",
                    message=f"Odd number of markdown code fences detected ({fence_count}). A code block may be unclosed.",
                    severity=LintSeverity.WARNING,
                    suggestion="Add closing '```' to balance markdown code fences.",
                )
            )

        # 4. XML / Semantic Tag Balance
        for tag in COMMON_TAGS:
            open_tags = len(re.findall(rf"<{tag}>", template_str, re.IGNORECASE))
            close_tags = len(re.findall(rf"</{tag}>", template_str, re.IGNORECASE))
            if open_tags != close_tags:
                issues.append(
                    LintIssue(
                        rule_id="UNBALANCED_TAG",
                        message=f"Unbalanced <{tag}> tags: found {open_tags} opening vs {close_tags} closing.",
                        severity=LintSeverity.WARNING,
                        suggestion=f"Ensure every <{tag}> tag has a matching </{tag}> tag.",
                    )
                )

        # 5. Injection & Safety Smell Check
        for idx, line in enumerate(lines, 1):
            for pattern, msg in INJECTION_PATTERNS:
                if re.search(pattern, line):
                    issues.append(
                        LintIssue(
                            rule_id="PROMPT_INJECTION_SMELL",
                            message=f"{msg} Found on line {idx}.",
                            line_number=idx,
                            severity=LintSeverity.WARNING,
                            suggestion="Isolate untrusted user input within delimiters (e.g. <user_query> ... </user_query>).",
                        )
                    )

        # 6. Formatting & Whitespace Smells
        trailing_ws_count = 0
        for idx, line in enumerate(lines, 1):
            if line.endswith(" ") or line.endswith("\t"):
                trailing_ws_count += 1

        if trailing_ws_count > 0:
            issues.append(
                LintIssue(
                    rule_id="TRAILING_WHITESPACE",
                    message=f"{trailing_ws_count} line(s) contain trailing whitespace.",
                    severity=LintSeverity.INFO,
                    suggestion="Trim trailing whitespace from lines to conserve tokens.",
                )
            )

        if re.search(r"\n{4,}", template_str):
            issues.append(
                LintIssue(
                    rule_id="EXCESSIVE_BLANK_LINES",
                    message="Template contains 3 or more consecutive empty lines.",
                    severity=LintSeverity.INFO,
                    suggestion="Normalize empty lines to at most 1 or 2 blank lines.",
                )
            )

        # Generate interpolated preview if variables are provided
        preview = template_str
        if variables:
            for k, val in variables.items():
                preview = preview.replace(f"{{{k}}}", str(val))

        errors_count = sum(1 for i in issues if i.severity == LintSeverity.ERROR)
        warnings_count = sum(1 for i in issues if i.severity == LintSeverity.WARNING)
        is_valid = errors_count == 0

        raw_chars = len(template_str)
        tokens_est = estimate_tokens(template_str)

        return LintReport(
            is_valid=is_valid,
            template_name=template_name,
            total_issues=len(issues),
            errors_count=errors_count,
            warnings_count=warnings_count,
            issues=issues,
            variables_found=vars_found,
            variables_missing=missing_vars,
            variables_unused=unused_vars,
            raw_character_count=raw_chars,
            estimated_token_count=tokens_est,
            interpolated_preview=preview,
        )
