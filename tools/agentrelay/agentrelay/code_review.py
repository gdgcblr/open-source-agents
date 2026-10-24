"""Deterministic code review and risk analysis engine."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from agentrelay.evidence import EvidenceStore, redact_secrets
from agentrelay.schemas import EvidenceRecord, Finding, InvestigationReport

# Concrete risk pattern definitions for deterministic code review
RISK_RULES = [
    {
        "id": "RULE_HARDCODED_SECRET",
        "name": "Hardcoded Secret or Token",
        "severity": "critical",
        "confidence": "medium",
        "patterns": [
            re.compile(r"sk-[a-zA-Z0-9]{20,}", re.IGNORECASE),
            re.compile(r"AIza[0-9A-Za-z-_]{35}"),
            re.compile(r"AKIA[0-9A-Z]{16}"),
            re.compile(r"gh[pousr]-[A-Za-z0-9_]{36,}"),
            re.compile(r"(api_key|secret|password|token)\s*=\s*['\"][a-zA-Z0-9_\-\.]{8,}['\"]", re.IGNORECASE),
        ],
        "explanation": "A hardcoded secret, token, or API key was detected in added lines. Committing credentials poses immediate security exposure.",
        "action": "Move credential to environment variables or secret manager immediately; rotate exposed keys.",
    },
    {
        "id": "RULE_SQL_INJECTION",
        "name": "Unparameterized SQL Query",
        "severity": "high",
        "confidence": "medium",
        "patterns": [
            re.compile(r"(execute|query)\s*\(\s*f['\"].*(SELECT|INSERT|UPDATE|DELETE).*{.*}", re.IGNORECASE),
            re.compile(r"(execute|query)\s*\(\s*['\"].*(SELECT|INSERT|UPDATE|DELETE).*['\"]\s*\+\s*", re.IGNORECASE),
            re.compile(r"(execute|query)\s*\(\s*['\"].*(SELECT|INSERT|UPDATE|DELETE).*['\"]\s*%\s*", re.IGNORECASE),
            re.compile(r"(query|sql|stmt|statement)\s*=\s*f['\"].*(SELECT|INSERT|UPDATE|DELETE).*{.*}", re.IGNORECASE),
            re.compile(r"(query|sql|stmt|statement)\s*=\s*['\"].*(SELECT|INSERT|UPDATE|DELETE).*['\"]\s*\+\s*", re.IGNORECASE),
        ],
        "explanation": "Dynamic SQL construction using string formatting or concatenation detected. This creates an unescaped SQL injection vector if user input reaches the query.",
        "action": "Use parameterized queries (e.g., cursor.execute(query, (param,))) or a type-safe ORM query builder.",
    },
    {
        "id": "RULE_COMMAND_INJECTION",
        "name": "Unsafe Shell Command Execution",
        "severity": "high",
        "confidence": "medium",
        "patterns": [
            re.compile(r"subprocess\.(run|Popen|check_output|call)\s*\(.*shell\s*=\s*True", re.IGNORECASE),
            re.compile(r"os\.system\s*\(", re.IGNORECASE),
            re.compile(r"os\.popen\s*\(", re.IGNORECASE),
        ],
        "explanation": "Execution of commands via a system shell (shell=True or os.system) detected. Shell interpolation allows arbitrary command injection if arguments contain untrusted characters.",
        "action": "Pass command arguments as a list to subprocess without shell=True, and sanitize all input arguments.",
    },
    {
        "id": "RULE_INSECURE_DESERIALIZATION",
        "name": "Insecure Deserialization",
        "severity": "high",
        "confidence": "medium",
        "patterns": [
            re.compile(r"pickle\.(loads|load)\s*\(", re.IGNORECASE),
            re.compile(r"yaml\.load\s*\(.*Loader\s*=\s*(yaml\.)?Loader", re.IGNORECASE),
            re.compile(r"_pickle\.(loads|load)\s*\(", re.IGNORECASE),
        ],
        "explanation": "Insecure deserialization using pickle or unsafe YAML loader detected. Unpickling untrusted byte streams allows arbitrary remote code execution.",
        "action": "Use safe serialization formats like JSON, or yaml.safe_load. Never unpickle untrusted data.",
    },
    {
        "id": "RULE_SILENT_ERROR_SUPPRESSION",
        "name": "Silent Exception Suppression",
        "severity": "low",
        "confidence": "medium",
        "patterns": [
            re.compile(r"except(\s+Exception)?\s*:\s*(pass|\.\.\.)\s*$", re.MULTILINE),
        ],
        "explanation": "Broad exception handling with 'pass' silently swallows failures, obscuring debugging and root-cause analysis during incidents.",
        "action": "Catch specific exception types and log errors with tracebacks rather than silently ignoring exceptions.",
    },
]


@dataclass
class DiffHunk:
    """A hunk within a patch diff."""

    header: str
    old_start: int
    old_length: int
    new_start: int
    new_length: int
    added_lines: List[Tuple[int, str]] = field(default_factory=list)
    removed_lines: List[Tuple[int, str]] = field(default_factory=list)
    raw_lines: List[str] = field(default_factory=list)


@dataclass
class ChangedFile:
    """A changed file in a patch."""

    old_path: Optional[str]
    new_path: Optional[str]
    is_binary: bool = False
    is_deleted: bool = False
    is_new: bool = False
    hunks: List[DiffHunk] = field(default_factory=list)


def parse_unified_diff(diff_text: str) -> List[ChangedFile]:
    """Safely parse unified git diff format into structured ChangedFile objects.

    Handles malformed diffs and binary files without crashing.
    """
    if not isinstance(diff_text, str) or not diff_text.strip():
        return []

    lines = diff_text.splitlines()
    files: List[ChangedFile] = []
    current_file: Optional[ChangedFile] = None
    current_hunk: Optional[DiffHunk] = None
    current_new_line_no = 1
    current_old_line_no = 1

    i = 0
    while i < len(lines):
        line = lines[i]

        # Check for diff header
        if line.startswith("diff --git "):
            current_hunk = None
            parts = line.split(" ")
            old_p = parts[2][2:] if len(parts) > 2 and parts[2].startswith("a/") else None
            new_p = parts[3][2:] if len(parts) > 3 and parts[3].startswith("b/") else None
            current_file = ChangedFile(old_path=old_p, new_path=new_p)
            files.append(current_file)
            i += 1
            continue

        if current_file is None:
            # Fallback for plain unified diff without diff --git
            if line.startswith("--- "):
                old_p = line[4:].strip().lstrip("a/")
                current_file = ChangedFile(old_path=old_p, new_path=None)
                files.append(current_file)
            i += 1
            continue

        if line.startswith("--- "):
            old_p = line[4:].strip()
            if old_p != "/dev/null":
                current_file.old_path = old_p.lstrip("a/")
            else:
                current_file.is_new = True
            i += 1
            continue

        if line.startswith("+++ "):
            new_p = line[4:].strip()
            if new_p != "/dev/null":
                current_file.new_path = new_p.lstrip("b/")
            else:
                current_file.is_deleted = True
            i += 1
            continue

        if "Binary files" in line and "differ" in line:
            current_file.is_binary = True
            i += 1
            continue

        # Check for hunk header @@ -old_start,old_len +new_start,new_len @@
        if line.startswith("@@"):
            match = re.search(r"@@\s*-(\d+)(?:,(\d+))?\s*\+(\d+)(?:,(\d+))?\s*@@", line)
            if match:
                old_start = int(match.group(1))
                old_len = int(match.group(2)) if match.group(2) else 1
                new_start = int(match.group(3))
                new_len = int(match.group(4)) if match.group(4) else 1
                current_new_line_no = new_start
                current_old_line_no = old_start
                current_hunk = DiffHunk(
                    header=line,
                    old_start=old_start,
                    old_length=old_len,
                    new_start=new_start,
                    new_length=new_len,
                )
                current_file.hunks.append(current_hunk)
            i += 1
            continue

        if current_hunk is not None:
            current_hunk.raw_lines.append(line)
            if line.startswith("+") and not line.startswith("+++"):
                current_hunk.added_lines.append((current_new_line_no, line[1:]))
                current_new_line_no += 1
            elif line.startswith("-") and not line.startswith("---"):
                current_hunk.removed_lines.append((current_old_line_no, line[1:]))
                current_old_line_no += 1
            else:
                # Context line
                current_new_line_no += 1
                current_old_line_no += 1

        i += 1

    if not files and lines:
        # Fallback: user provided plain code snippet instead of diff format
        code_indicators = ("def ", "class ", "import ", "from ", "return ", "=", "function", "var ", "const ", "let ")
        looks_like_code = any(any(ind in l for ind in code_indicators) for l in lines)
        if looks_like_code:
            plain_hunk = DiffHunk(
                header="@@ -0,0 +1,{} @@".format(len(lines)),
                old_start=0,
                old_length=0,
                new_start=1,
                new_length=len(lines),
                added_lines=[(idx + 1, l) for idx, l in enumerate(lines)],
                raw_lines=lines,
            )
            files.append(
                ChangedFile(
                    old_path=None,
                    new_path="submitted_code.py",
                    is_new=True,
                    hunks=[plain_hunk],
                )
            )

    return files


def run_deterministic_review(
    diff_text: str,
    commit_id: Optional[str] = None,
    service: Optional[str] = None,
) -> Tuple[InvestigationReport, EvidenceStore]:
    """Run deterministic risk analysis on a diff.

    Parses changed lines, checks concrete risk rules, captures evidence records,
    and returns an InvestigationReport and an EvidenceStore.
    """
    evidence_store = EvidenceStore()
    findings: List[Finding] = []
    unknowns: List[str] = []
    recommendations: List[str] = []

    files = parse_unified_diff(diff_text)

    if not files:
        # Malformed or empty diff
        report = InvestigationReport(
            summary="Code review completed: empty or unsupported diff format provided.",
            findings=[],
            unknowns=["Diff contains no recognized unified diff hunks or code changes."],
            recommendations=["Verify that the patch was generated using 'git diff' or unified format."],
            execution_metadata={"file_count": 0, "deterministic_rules_run": len(RISK_RULES)},
        )
        return report, evidence_store

    has_test_changes = False
    production_files_changed = 0
    evidence_counter = 1

    for cfile in files:
        file_path = cfile.new_path or cfile.old_path or "unknown_file"

        # Check if tests are changed
        if "test" in file_path.lower() or "spec" in file_path.lower():
            has_test_changes = True
        elif not cfile.is_binary:
            production_files_changed += 1

        if cfile.is_binary:
            continue

        for hunk in cfile.hunks:
            # Check added lines against risk rules
            for line_no, line_content in hunk.added_lines:
                for rule in RISK_RULES:
                    matched = False
                    for pattern in rule["patterns"]:
                        if pattern.search(line_content):
                            matched = True
                            break

                    if matched:
                        ev_id = f"diff-ev-{evidence_counter:03d}"
                        evidence_counter += 1

                        ev_record = EvidenceRecord(
                            id=ev_id,
                            source_type="diff",
                            content=f"File: {file_path}:{line_no}\n+ {line_content.strip()}",
                            service=service,
                            commit_id=commit_id,
                            metadata={
                                "file_path": file_path,
                                "line_number": line_no,
                                "rule_id": rule["id"],
                                "heuristic": True,
                            },
                        )
                        evidence_store.add(ev_record)

                        claim = (
                            f"[Heuristic] {rule['name']} detected in {file_path}:{line_no}"
                        )
                        finding = Finding(
                            claim=claim,
                            severity=rule["severity"],
                            confidence=rule["confidence"],
                            evidence_ids=[ev_id],
                            explanation=f"{rule['explanation']} Matched pattern in {file_path}:{line_no}.",
                            recommended_next_action=rule["action"],
                        )
                        findings.append(finding)

    # Check for test coverage omission
    if production_files_changed > 0 and not has_test_changes:
        ev_id = f"diff-ev-{evidence_counter:03d}"
        evidence_counter += 1
        ev_record = EvidenceRecord(
            id=ev_id,
            source_type="diff",
            content=f"Diff modifies {production_files_changed} production files but includes no changes to test files or specs.",
            service=service,
            commit_id=commit_id,
            metadata={"production_files_count": production_files_changed, "has_test_changes": False},
        )
        evidence_store.add(ev_record)

        findings.append(
            Finding(
                claim="Production code modified without accompanying unit or integration tests",
                severity="medium",
                confidence="low",
                evidence_ids=[ev_id],
                explanation=(
                    f"{production_files_changed} production file(s) changed without corresponding "
                    "modifications in test files, increasing regression risk."
                ),
                recommended_next_action="Add regression and edge-case unit tests covering the modified functions.",
            )
        )

    # Unknowns and limitations
    unknowns.append("Static regex heuristics cannot verify dynamic runtime sanitization or type invariants.")
    unknowns.append("Full architectural impact cannot be determined from diff alone without complete repository context.")

    # High-level recommendations
    if findings:
        recommendations.append("Address critical and high severity findings before deploying code to production.")
    else:
        recommendations.append("Deterministic checks found no known critical risk patterns. Proceed with standard testing and peer review.")

    summary = (
        f"Deterministic code review inspected {len(files)} file(s). "
        f"Found {len(findings)} potential issue(s) across {len(evidence_store.all_records())} evidence citation(s)."
    )

    report = InvestigationReport(
        summary=summary,
        findings=findings,
        unknowns=unknowns,
        recommendations=recommendations,
        execution_metadata={
            "files_inspected": len(files),
            "production_files_changed": production_files_changed,
            "has_test_changes": has_test_changes,
            "rules_checked": len(RISK_RULES),
            "commit_id": commit_id,
            "service": service,
        },
    )

    return report, evidence_store
