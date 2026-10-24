import json
import re
import urllib.error
import urllib.request
from pathlib import Path

from .sbom import bom_ref, collect_components, has_lockfile

OSV_URL = "https://api.osv.dev/v1/querybatch"
OSV_TIMEOUT_SECONDS = 20
OSV_BATCH_SIZE = 500
OSV_ECOSYSTEMS = {"PyPI", "npm", "Go"}
MAX_LISTED = 15
FROM_LINE = re.compile(r"^FROM\s+(?:--\S+\s+)?(\S+)(?:\s+AS\s+(\S+))?", re.IGNORECASE)
SECRET_ENV = re.compile(r"^(?:ENV|ARG)\s+(\w*(?:KEY|TOKEN|SECRET|PASSWORD|PASSWD)\w*)\s*[= ]\s*([^\s$]\S*)", re.IGNORECASE)
PIPE_TO_SHELL = re.compile(r"(?:curl|wget)[^|\n]*\|\s*(?:sudo\s+)?(?:ba)?sh\b", re.IGNORECASE)


def _finding(severity: str, message: str) -> dict:
    return {"severity": severity, "message": message}


def _capped(items: list[str], template: str) -> list[dict]:
    findings = [_finding("warn", template.format(item)) for item in items[:MAX_LISTED]]
    if len(items) > MAX_LISTED:
        findings.append(_finding("warn", f"... and {len(items) - MAX_LISTED} more."))
    return findings


def dockerfile_paths(root: Path) -> list[Path]:
    found = []
    for path in sorted(root.iterdir()) if root.is_dir() else []:
        lowered = path.name.lower()
        if path.is_file() and (lowered == "dockerfile" or lowered.startswith("dockerfile.") or lowered.endswith(".dockerfile")):
            found.append(path)
    return found


def _logical_lines(text: str) -> list[str]:
    lines = []
    current = ""
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.endswith("\\"):
            current += stripped[:-1].strip() + " "
            continue
        lines.append((current + stripped).strip())
        current = ""
    if current:
        lines.append(current.strip())
    return lines


def dockerfile_findings(path: Path) -> list[dict]:
    findings = []
    lines = _logical_lines(path.read_text(encoding="utf-8", errors="replace"))
    stages = set()
    has_user = False
    for line in lines:
        from_match = FROM_LINE.match(line)
        if from_match:
            image, alias = from_match.groups()
            if alias:
                stages.add(alias.lower())
            if image.lower() == "scratch" or image.lower() in stages or "$" in image or "@sha256:" in image:
                continue
            tag = image.rsplit("/", 1)[-1].partition(":")[2]
            if not tag or tag == "latest":
                findings.append(_finding("warn", f"{path.name}: base image '{image}' has no pinned tag."))
            continue
        upper = line.upper()
        if upper.startswith("USER ") and line.split(None, 1)[1].strip().lower() not in ("root", "0"):
            has_user = True
        secret = SECRET_ENV.match(line)
        if secret:
            findings.append(_finding("high", f"{path.name}: secret-like variable '{secret.group(1)}' is set in the image."))
        if PIPE_TO_SHELL.search(line):
            findings.append(_finding("warn", f"{path.name}: downloads a script and pipes it to a shell."))
    if lines and not has_user:
        findings.append(_finding("warn", f"{path.name}: no non-root USER set, so the container runs as root."))
    return findings


def osv_query(components: list[dict]) -> list[list[str]]:
    results: list[list[str]] = []
    for start in range(0, len(components), OSV_BATCH_SIZE):
        chunk = components[start:start + OSV_BATCH_SIZE]
        payload = {
            "queries": [
                {"package": {"name": item["name"], "ecosystem": item["ecosystem"]}, "version": item["version"]}
                for item in chunk
            ]
        }
        request = urllib.request.Request(
            OSV_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=OSV_TIMEOUT_SECONDS) as response:
            body = json.loads(response.read().decode("utf-8"))
        for entry in body.get("results", []):
            results.append([vuln["id"] for vuln in entry.get("vulns", [])])
    return results


def check_posture(project_path: str, vuln_scan: bool = False, fetch=osv_query) -> dict:
    root = Path(project_path).resolve()
    if not root.is_dir():
        return {"status": "error", "findings": [_finding("high", f"Not a directory: {project_path}")], "components": [], "vulnerabilities": [], "vuln_scan": "skipped"}
    components = collect_components(str(root))
    findings: list[dict] = []
    findings.extend(_capped(
        [f"{item['name']} ({item['source']}: {item['spec']})" for item in components if not item["pinned"]],
        "Dependency not pinned to an exact version: {}",
    ))
    if any(item["ecosystem"] == "npm" for item in components) and not has_lockfile(root):
        findings.append(_finding("warn", "package.json has no lockfile (package-lock.json, yarn.lock or pnpm-lock.yaml)."))
    for dockerfile in dockerfile_paths(root):
        findings.extend(dockerfile_findings(dockerfile))
    vulnerabilities: list[dict] = []
    scan_state = "skipped"
    if vuln_scan:
        scannable = [item for item in components if item["pinned"] and item["ecosystem"] in OSV_ECOSYSTEMS]
        try:
            lookups = fetch(scannable) if scannable else []
            scan_state = "done"
            for item, ids in zip(scannable, lookups):
                for vuln_id in ids:
                    vulnerabilities.append({"id": vuln_id, "ref": bom_ref(item)})
                    findings.append(_finding("high", f"Known vulnerability {vuln_id} in {item['name']} {item['version']}."))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            scan_state = "failed"
            findings.append(_finding("warn", f"Vulnerability lookup failed and was skipped: {exc}"))
    severities = {item["severity"] for item in findings}
    status = "fail" if "high" in severities else ("warn" if "warn" in severities else "pass")
    return {
        "status": status,
        "findings": findings,
        "components": components,
        "vulnerabilities": vulnerabilities,
        "vuln_scan": scan_state,
    }
