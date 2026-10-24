"""Evidence-backed investigation and human policy, independent of ADK/Gemini."""
from datetime import date
from pathlib import Path
import re

from .advisories import match_runtime, version_tuple
from .engine import analyze_logs, redact, redacted_lines, MAX_EXCERPT

INJECTION = re.compile(r"(?i)ignore (?:all |previous |system )*instructions|system prompt|you are now|<\|(?:system|assistant)|do not escalate")
SUSPICIOUS = re.compile(r"(?i)union\s+select|\.\./|<script\b|sql injection|path traversal|\b401 unauthorized\b|\b403 forbidden\b")
COMPROMISE = re.compile(r"(?i)webshell|reverse shell|exfiltrat|unexpected child process|unauthorized process")
RUNTIME = re.compile(r"(?i)\b(php|nodejs|node\.js|node)\s*(?:version\s*[:=]?\s*|[/:=]\s*|\s+)v?(\d+\.\d+\.\d+(?:[-+][\w.-]+)?)")


def investigate(log_text: str, product: str = "", version: str = "", internet_facing: bool = False,
                production: bool = False, *, catalog_path: Path | None = None, today: date | None = None) -> dict:
    if not isinstance(product, str) or not isinstance(version, str) or type(internet_facing) is not bool or type(production) is not bool:
        raise ValueError("Runtime fields must be strings and exposure fields must be booleans")
    analysis = analyze_logs(log_text)
    product = product.lower()
    # Do not reflect arbitrary runtime metadata (which may contain secrets).
    safe_product = product if product in {"php", "nodejs"} else "unknown"
    try:
        version_tuple(version)
        safe_version = version
    except ValueError:
        safe_version = "unknown"
    runtime = match_runtime(product, version, path=catalog_path, today=today)
    ledger = {"R1": {"kind": "user_metadata", "product": safe_product, "version": safe_version,
                     "internet_facing": internet_facing, "production": production,
                     "trust": "User supplied; deployed binary and configuration require human verification."}}
    findings = []
    unknowns = list(runtime["issues"])
    reasons = []
    escalation_refs = []

    def add(kind, text, refs):
        findings.append({"id": f"F{len(findings) + 1}", "kind": kind, "text": text, "evidence_refs": refs})

    for match in runtime["matches"]:
        ref = "A:" + match["cve"]
        ledger[ref] = {"kind": "advisory", **match}
        qualifier = "Historical snapshot" if runtime["status"] == "UNKNOWN" else "Curated snapshot"
        add("runtime", f"{qualifier}: {safe_product} {safe_version} is {match['status']} for {match['cve']} only; this does not establish exploitation or overall safety.", ["R1", ref])
        if match["status"] == "AFFECTED" and match["severity"] in {"critical", "high"}:
            reasons.append("An affected runtime has an officially high or critical advisory; urgent human review is required to assess applicability and exposure.")
            escalation_refs.extend(["R1", ref])
    for i, notice in enumerate(runtime.get("notices", []), 1):
        ref = f"N{i}"
        ledger[ref] = {"kind": "publisher_notice", **notice}
        add("coverage_gap", notice["note"], [ref])
        unknowns.append("Publisher follow-up has no complete curated version ranges; manual advisory verification is required.")

    safe_lines = redacted_lines(log_text)
    counts = {}
    omitted = False
    for number, line in enumerate(log_text.splitlines(), 1):
        ref = f"L{number}"

        def observe(kind, description, urgent=False):
            nonlocal omitted
            counts[kind] = counts.get(kind, 0) + 1
            # Scan all bounded lines for policy; keep only three examples per kind.
            if counts[kind] > 3:
                omitted = True
                return
            ledger[ref] = {"kind": "log", "line": number, "excerpt": safe_lines[number - 1][:MAX_EXCERPT], "trust": "Untrusted log statement, not independently corroborated."}
            add(kind, description, [ref])
            if urgent:
                reasons.append(description)
                escalation_refs.append(ref)

        if INJECTION.search(line):
            observe("injection", "Instruction-like log content was treated as data; no instructions from logs were executed.")
        if COMPROMISE.search(line):
            observe("suspected_compromise", "A log mentions a possible compromise or exfiltration indicator; authenticity and impact require urgent human investigation.", True)
        if SUSPICIOUS.search(line):
            observe("suspicious", "A suspicious request or authorization-failure pattern appears in the log; exploitation is not established.")
            unknowns.append("Suspicious activity needs request, identity, and host telemetry correlation.")
        if redact(line) != line or "[REDACTED_PRIVATE_KEY]" in safe_lines[number - 1]:
            observe("sensitive_data", "Possible credentials or sensitive authentication data appear in logs; review exposure and human-approved credential handling.", True)
        for observed_product, observed_version in RUNTIME.findall(line):
            observed_product = "php" if observed_product.lower() == "php" else "nodejs"
            if observed_product != product or observed_version != version:
                observe("conflict", "Log runtime metadata conflicts with the supplied runtime; verify deployment identity before diagnosis.")
                unknowns.append("Conflicting runtime evidence; no deployed version has been established.")
    for signal in analysis["top_signals"]:
        refs = []
        for entry in signal["evidence"]:
            ref = f"L{entry['line']}"
            ledger.setdefault(ref, {"kind": "log", **entry, "trust": "Untrusted log statement."})
            refs.append(ref)
        add("operational_hypothesis", signal["hypothesis"] + " This is an unverified operational hypothesis.", refs)
    if not log_text.strip():
        unknowns.append("No log evidence supplied; collect a bounded incident-time sample.")
    unknowns = sorted(set(unknowns))
    reasons = sorted(set(reasons))
    decision = "ESCALATE" if reasons else "HOLD" if unknowns else "PASS"
    severity = "critical" if any(m["severity"] == "critical" and m["status"] == "AFFECTED" for m in runtime["matches"]) else "high" if reasons else "undetermined"
    next_steps = ["Verify the deployed runtime, vendor backports, exposure, and publisher advisories.",
                  "Preserve relevant logs and correlate request IDs with host, identity, and network telemetry.",
                  "Have an authorized responder decide containment and patching; no action or incident closure is automated."]
    assumptions = ["Runtime and exposure metadata are user assertions.", "Log authenticity is not established.", "Snapshot coverage is partial; FIXED refers only to listed CVEs."]
    return {"schema_version": 1, "mode": "offline_deterministic", "decision": decision,
            "summary": f"{decision}: scoped runtime assessment {runtime['status']}; compromise is not confirmed.",
            "runtime": runtime, "severity": severity, "findings": findings, "evidence": ledger,
            "unknowns": unknowns, "assumptions": assumptions,
            "compromise": "NOT_CONFIRMED", "next_steps": next_steps,
            "escalation": {"required": decision == "ESCALATE", "summary": "Urgent human review required." if reasons else "No mandatory escalation triggered in this bounded sample.",
                           "severity": severity, "rationale": reasons, "evidence_refs": sorted(set(escalation_refs)),
                           "unknowns": unknowns, "assumptions": assumptions, "next_steps": next_steps,
                           "required_human_decision": "Assess incident scope, containment, credential handling, and remediation priority." if reasons else "Verify evidence and decide whether further investigation is needed."},
            "credibility": {"valid": True, "rejected_claims": 0},
            "evidence_examples_truncated": omitted, "analysis": analysis}
