"""Eval cases: sample projects plus the outcome each one is expected to produce.

Expectations are written from what each sample is *meant* to demonstrate, not copied from a
run. The offline tests (tests/test_evals.py) and the ADK eval set (build_samples.py) share them.
"""

import os
import shutil
from pathlib import Path

SAMPLES = Path(__file__).parent / "samples"
# Assembled from parts so no key-like text is ever committed.
FAKE_KEY = "AIza" + "Q" * 35

# Fake credentials, assembled from parts like FAKE_KEY. Nothing here works anywhere.
VULN_GOOGLE_KEY = "AIza" + "R" * 35
VULN_GITHUB_TOKEN = "ghp_" + "S" * 36
VULN_AWS_KEY = "AKIA" + "T" * 16
VULN_PASSWORD = "hunter2" * 3
VULN_SECRETS = [VULN_GOOGLE_KEY, VULN_GITHUB_TOKEN, VULN_AWS_KEY, VULN_PASSWORD]


def write_vulnerabilities(target: Path) -> None:
    """Add fake credentials and risky code to the vulnerable sample.

    Written at build time (into the git-ignored .generated/ folder) and assembled from parts, so
    no key-like text or dangerous call is ever committed or flagged in this repository itself.
    """
    (target / ".env").write_text(f"GOOGLE_API_KEY={VULN_GOOGLE_KEY}\nDB_HOST=localhost\n")
    (target / "app.py").write_text(
        "import os\nimport subprocess\n\n"
        f'API_KEY = "{VULN_GOOGLE_KEY}"\n'
        f'AWS_KEY = "{VULN_AWS_KEY}"\n'
        'PASSWORD = "' + VULN_PASSWORD + '"\n\n\n'
        "def run(user_input, code):\n"
        "    os." + "system(user_input)\n"
        "    subprocess.run(user_input, shell=" + "True)\n"
        "    ex" + "ec(code)\n"
        "    return ev" + "al(user_input)\n"
    )
    (target / "config.json").write_text(f'{{"github_token": "{VULN_GITHUB_TOKEN}"}}\n')
    (target / "deploy.sh").write_text("#!/bin/sh\nrm -r" + "f /tmp/old-build\n")
    (target / "server.js").write_text('const cp = require("child_' + 'process");\ncp.exec(process.argv[2]);\n')
    (target / "id_rsa").write_text("-----BEGIN RSA PRIVATE" + " KEY-----\nZmFrZSBrZXkgZm9yIHRlc3Rpbmc=\n")
    os.symlink("/etc", target / "etc-link")  # points outside the repo: must never be followed


CASES = [
    {
        "id": "excellent",
        "folder": "excellent-agent",
        "source": "excellent-agent",
        "expect": {"verdict": "ready", "min_score": 95, "must_fail": [],
                   "must_pass": ["manifest_present", "sections_present", "no_secrets", "folder_name_ok"]},
    },
    {
        "id": "missing_install_steps",
        "folder": "missing-install-agent",
        "source": "missing-install-agent",
        "expect": {"verdict": "needs_changes", "max_score": 84,
                   "must_fail": ["manifest_present", "env_example_present", "sections_present",
                                 "run_command_documented"],
                   "must_pass": ["no_secrets", "folder_name_ok", "sections_not_thin"]},
    },
    {
        "id": "leaked_api_key",
        "folder": "leaked-key-agent",
        "source": "leaked-key-agent",
        "expect": {"verdict": "needs_changes", "must_fail": ["no_secrets"],
                   "must_pass": ["manifest_present", "sections_present", "folder_name_ok"]},
    },
    {
        "id": "wrong_folder_name",
        "folder": "Bad_Name_Agent",
        "source": "excellent-agent",  # identical content, only the folder name is wrong
        "expect": {"verdict": "needs_changes", "must_fail": ["folder_name_ok"],
                   "must_pass": ["manifest_present", "sections_present", "no_secrets"]},
    },
    {
        "id": "minimal_readme",
        "folder": "minimal-agent",
        "source": "minimal-agent",
        "expect": {"verdict": "needs_changes", "max_score": 70,
                   "must_fail": ["manifest_present", "sections_present", "env_example_present",
                                 "run_command_documented", "gitignore_covers_secrets_and_venv"],
                   "must_pass": ["no_secrets", "folder_name_ok"]},
    },
    {
        "id": "vulnerable_project",
        "folder": "vulnerable-agent",
        "source": "vulnerable-agent",
        "extras": write_vulnerabilities,  # fake credentials, risky code, key file, outside symlink
        "expect": {"verdict": "needs_changes", "max_score": 70,
                   "must_fail": ["no_secrets", "no_risky_code", "gitignore_covers_secrets_and_venv",
                                 "deps_pinned", "env_example_present"],
                   "must_pass": ["manifest_present", "sections_present", "no_placeholders",
                                 "python_version_stated", "run_command_documented", "folder_name_ok"]},
    },
]


def build_samples(dest: Path) -> None:
    """Copy the samples into dest under each case's folder name, filling in the fake key."""
    dest = Path(dest)
    if dest.exists():
        shutil.rmtree(dest)
    for case in CASES:
        target = dest / case["folder"]
        shutil.copytree(SAMPLES / case["source"], target)
        for path in target.rglob("*"):
            if path.is_file():
                text = path.read_text()
                if "{{FAKE_KEY}}" in text:
                    path.write_text(text.replace("{{FAKE_KEY}}", FAKE_KEY))
        if case.get("extras"):
            case["extras"](target)


def outcome(report, case) -> list:
    """Problems found when comparing a ReviewReport with the case's expectations (empty = pass)."""
    expect, problems = case["expect"], []
    failed = {f.id for f in report.failures}
    if report.verdict != expect["verdict"]:
        problems.append(f"verdict {report.verdict}, expected {expect['verdict']}")
    if "min_score" in expect and report.overall_score < expect["min_score"]:
        problems.append(f"score {report.overall_score} below {expect['min_score']}")
    if "max_score" in expect and report.overall_score > expect["max_score"]:
        problems.append(f"score {report.overall_score} above {expect['max_score']}")
    problems += [f"expected {i} to fail" for i in expect["must_fail"] if i not in failed]
    problems += [f"expected {i} to pass" for i in expect["must_pass"] if i in failed]
    if not expect["must_fail"] and report.failures:
        problems.append(f"expected no failures, got {sorted(failed)}")
    return problems
