"""Portable JSON, Markdown, terminal summaries, and explicit retest comparison."""

import json
from pathlib import Path

from .contract import DoctorError


def summary(report):
    lines = [
        "FIRST RUN DOCTOR",
        f"Verification: {report['verification'].upper()}",
        f"Execution: {report['execution']['status']}",
        "",
    ]
    for check in report["checks"]:
        lines.append(
            f"{check['status'].upper():7} {check['id']:7} {check['label']}: {check['detail']}"
        )
    lines.extend(["", "Next step: " + report["diagnosis"]["next_step"]])
    if "jev" in report:
        value = report["jev"]
        lines.append("Jev (advisory): " + value.get("category", value.get("reason", "unavailable")))
    return "\n".join(lines)


def _cell(value):
    # Prevent target-controlled content from injecting Markdown links, images or HTML.
    text = str(value).replace("\n", " ").replace("\r", " ")
    for char in "&<>|`[]":
        text = text.replace(char, f"&#{ord(char)};")
    return text


def markdown(report):
    lines = [
        "# FirstRun Doctor report",
        "",
        f"**Verification: {report['verification'].upper()}**",
        "",
        f"Run: `{report['run_id']}`",
        "",
        f"Execution: {_cell(report['execution']['status'])}",
        "",
        "| Check | Result | Evidence |",
        "| --- | --- | --- |",
    ]
    for check in report["checks"]:
        lines.append(
            f"| {_cell(check['id'] + ': ' + check['label'])} | {check['status']} | {_cell(check['detail'])} |"
        )
    lines.extend(
        [
            "",
            "## Next step",
            "",
            _cell(report["diagnosis"]["next_step"]),
            "",
            "## Evidence record",
            "",
            f"Contract SHA-256: `{report['contract_sha256']}`",
            "",
            f"Source SHA-256: `{report.get('source', {}).get('sha256', 'not captured')}`",
            "",
            "See the accompanying JSON for command, interpreter, timing, and bounded redacted logs.",
            "",
            "Passing verifies only the declared checks. Trusted local code runs as the current OS user.",
            "",
        ]
    )
    return "\n".join(lines)


def write_reports(report, output):
    directory = Path(output)
    # Never overwrite reports or follow a preexisting output directory/symlink.
    try:
        directory.mkdir(parents=True, exist_ok=False)
        (directory / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
        (directory / "report.md").write_text(markdown(report))
    except OSError as exc:
        raise DoctorError(f"Cannot create a new report directory: {exc}") from exc


def compare(before, after):
    for report in (before, after):
        if (
            not isinstance(report, dict)
            or report.get("schema_version") != 1
            or not isinstance(report.get("checks"), list)
            or not isinstance(report.get("interpreter"), dict)
        ):
            raise DoctorError("Expected a Doctor schema_version=1 report")
    changed = [
        key
        for key in ("contract_sha256", "command", "interpreter")
        if before.get(key) != after.get(key)
    ]
    old = {c["id"]: c["status"] for c in before["checks"]}
    transitions = [
        {"id": c["id"], "before": old.get(c["id"], "not_checked"), "after": c["status"]}
        for c in after["checks"]
    ]
    return {
        "schema_version": 1,
        "comparable": not changed,
        "changed_expectations": changed,
        "before": before["verification"],
        "after": after["verification"],
        "checks": transitions,
        "note": "Equivalent retest"
        if not changed
        else "Expectations or runtime changed; do not infer a verified fix.",
    }
