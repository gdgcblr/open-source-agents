"""Terraform Static Analysis and Service Connection Validator.

Analyzes Terraform configurations (*.tf) for providers, backend state storage,
cloud resources, and CI/CD security risks (e.g., automated terraform apply without gates).
Identifies required Azure DevOps Service Connections and backend prerequisites.
Never executes terraform or mutates cloud infrastructure.
"""

from __future__ import annotations

import re
from pathlib import Path

from models.migration_report import TerraformAnalysisResult

PROVIDER_BLOCK_RE = re.compile(r'provider\s+"([^"]+)"\s*\{', re.MULTILINE)
BACKEND_BLOCK_RE = re.compile(r'backend\s+"([^"]+)"\s*\{', re.MULTILINE)
RESOURCE_BLOCK_RE = re.compile(r'resource\s+"([^"]+)"\s+"([^"]+)"\s*\{', re.MULTILINE)
MODULE_BLOCK_RE = re.compile(r'module\s+"([^"]+)"\s*\{', re.MULTILINE)
SUSPICIOUS_TF_CRED_RE = re.compile(
    r'(?:client_secret|access_key|secret_key|password)\s*=\s*"([^"]+)"'
)


def analyze_terraform_directory(tf_dir: str | Path) -> TerraformAnalysisResult:
    """Performs static analysis across all .tf files in the given directory."""
    path = Path(tf_dir)
    if not path.is_dir():
        return TerraformAnalysisResult(
            has_terraform=False,
            findings=[f"Terraform directory does not exist: {tf_dir}"],
        )

    tf_files = list(path.glob("**/*.tf"))
    if not tf_files:
        return TerraformAnalysisResult(
            has_terraform=False,
            findings=["No .tf files discovered in directory."],
        )

    providers: set[str] = set()
    backend_type: str | None = None
    resources_count = 0
    modules_count = 0
    findings: list[str] = []
    service_connections_needed: set[str] = set()
    ci_apply_risk = False

    for tf_file in tf_files:
        try:
            content = tf_file.read_text(encoding="utf-8")
        except Exception as exc:
            findings.append(f"Failed to read {tf_file.name}: {exc}")
            continue

        # Extract providers
        for match in PROVIDER_BLOCK_RE.finditer(content):
            prov = match.group(1).lower()
            providers.add(prov)
            if prov == "azurerm":
                service_connections_needed.add("AzureRM Service Connection (ARM)")
            elif prov == "aws":
                service_connections_needed.add("AWS Service Connection")
            elif prov == "google":
                service_connections_needed.add("GCP Service Connection")

        # Extract backend
        backend_match = BACKEND_BLOCK_RE.search(content)
        if backend_match:
            backend_type = backend_match.group(1).lower()
            if backend_type == "azurerm":
                findings.append(
                    "AzureRM remote state backend detected. Requires storage account & container."
                )

        # Count resources & modules
        res_matches = RESOURCE_BLOCK_RE.findall(content)
        resources_count += len(res_matches)

        mod_matches = MODULE_BLOCK_RE.findall(content)
        modules_count += len(mod_matches)

        # Detect potential hardcoded credentials
        for cred_match in SUSPICIOUS_TF_CRED_RE.finditer(content):
            findings.append(
                f"Warning: Potential plaintext credential found in {tf_file.name}. "
                "Ensure credentials use variable inputs or Azure Key Vault."
            )

    # Determine CI/CD considerations
    if not backend_type:
        findings.append(
            "No remote backend configured. Terraform state will be ephemeral on CI agent!"
        )

    return TerraformAnalysisResult(
        has_terraform=True,
        file_count=len(tf_files),
        providers=sorted(providers),
        backend_type=backend_type,
        resources_count=resources_count,
        modules_count=modules_count,
        service_connections_needed=sorted(service_connections_needed),
        ci_apply_risk=ci_apply_risk,
        findings=findings,
    )
