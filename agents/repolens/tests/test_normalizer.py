"""
RepoLens — Unit Tests: Finding Normalizer
"""
import pytest
from backend.scanner.normalizer import normalize_trivy, normalize_semgrep
from backend.models import Finding


# ---------------------------------------------------------------------------
# Trivy
# ---------------------------------------------------------------------------

TRIVY_VULN_JSON = {
    "Results": [
        {
            "Target": "package.json",
            "Type": "npm",
            "Vulnerabilities": [
                {
                    "VulnerabilityID": "CVE-2022-24999",
                    "PkgName": "express",
                    "InstalledVersion": "4.16.4",
                    "FixedVersion": "4.18.2",
                    "Severity": "HIGH",
                    "Title": "ReDoS in express",
                    "References": ["https://nvd.nist.gov/vuln/detail/CVE-2022-24999"],
                }
            ],
        }
    ]
}

TRIVY_SECRET_JSON = {
    "Results": [
        {
            "Target": "config/env/development.js",
            "Secrets": [
                {
                    "Category": "generic",
                    "RuleID": "secret-db-url",
                    "Title": "Database connection string with credentials",
                    "Match": "mongodb://admin:supersecretpassword@localhost/db",
                    "StartLine": 5,
                    "EndLine": 5,
                }
            ],
        }
    ]
}

TRIVY_MISCONF_JSON = {
    "Results": [
        {
            "Target": "Dockerfile",
            "Misconfigurations": [
                {
                    "ID": "DS002",
                    "Title": "Running as root",
                    "Severity": "HIGH",
                    "Description": "Container should not run as root user",
                    "Resolution": "Add 'USER nonroot' to Dockerfile",
                }
            ],
        }
    ]
}


class TestNormalizeTrivy:

    def test_vulnerability_is_normalized(self):
        findings = normalize_trivy(TRIVY_VULN_JSON)
        assert len(findings) == 1
        f = findings[0]
        assert f.severity == "HIGH"
        assert f.category == "dependency"
        assert f.scanner == "trivy"
        assert f.rule_id == "CVE-2022-24999"
        assert f.provenance == "scanner"
        assert "express" in f.evidence
        assert f.source_url is not None

    def test_vulnerability_remediation_includes_fixed_version(self):
        findings = normalize_trivy(TRIVY_VULN_JSON)
        assert "4.18.2" in findings[0].remediation

    def test_secret_is_normalized_and_redacted(self):
        findings = normalize_trivy(TRIVY_SECRET_JSON)
        assert len(findings) == 1
        f = findings[0]
        assert f.category == "secret"
        assert f.severity == "HIGH"
        assert f.provenance == "scanner"
        # The raw password should be redacted
        assert "supersecretpassword" not in (f.evidence or "")

    def test_misconfiguration_normalized(self):
        findings = normalize_trivy(TRIVY_MISCONF_JSON)
        assert len(findings) == 1
        f = findings[0]
        assert f.category == "misconfiguration"
        assert f.severity == "HIGH"
        assert "root" in f.remediation.lower()

    def test_empty_results(self):
        assert normalize_trivy({}) == []
        assert normalize_trivy({"Results": []}) == []

    def test_unknown_severity_maps_to_unknown(self):
        data = {
            "Results": [
                {
                    "Target": "go.sum",
                    "Vulnerabilities": [
                        {
                            "VulnerabilityID": "CVE-9999",
                            "PkgName": "somepkg",
                            "InstalledVersion": "1.0",
                            "FixedVersion": "",
                            "Severity": "SOME_NEW_LEVEL",
                            "Title": "Unknown severity test",
                        }
                    ],
                }
            ]
        }
        findings = normalize_trivy(data)
        assert findings[0].severity == "UNKNOWN"

    def test_finding_has_unique_ids(self):
        findings = normalize_trivy(TRIVY_VULN_JSON)
        ids = [f.finding_id for f in findings]
        assert len(ids) == len(set(ids))


# ---------------------------------------------------------------------------
# Semgrep
# ---------------------------------------------------------------------------

SEMGREP_JSON = {
    "results": [
        {
            "check_id": "javascript.lang.security.audit.prototype-pollution",
            "path": "app/routes/profile.js",
            "start": {"line": 27},
            "end": {"line": 32},
            "extra": {
                "message": "Prototype pollution via unvalidated merge of user input",
                "severity": "ERROR",
                "lines": "_.extend(user, req.body)",
                "metadata": {
                    "cwe": ["CWE-1321"],
                    "fix": "Use allowlist of permitted fields",
                },
            },
        }
    ],
    "errors": [],
}


class TestNormalizeSemgrep:

    def test_sast_finding_normalized(self):
        findings = normalize_semgrep(SEMGREP_JSON)
        assert len(findings) == 1
        f = findings[0]
        assert f.category == "sast"
        assert f.scanner == "semgrep"
        assert f.severity == "HIGH"  # ERROR -> HIGH
        assert f.provenance == "scanner"
        assert f.file_path == "app/routes/profile.js"
        assert f.line_start == 27

    def test_semgrep_empty(self):
        assert normalize_semgrep({}) == []
        assert normalize_semgrep({"results": []}) == []

    def test_semgrep_warning_maps_to_medium(self):
        data = {
            "results": [
                {
                    "check_id": "some-rule",
                    "path": "app.js",
                    "start": {"line": 1},
                    "end": {"line": 1},
                    "extra": {
                        "message": "Warning-level finding",
                        "severity": "WARNING",
                        "lines": "var x = 1",
                        "metadata": {},
                    },
                }
            ]
        }
        findings = normalize_semgrep(data)
        assert findings[0].severity == "MEDIUM"
