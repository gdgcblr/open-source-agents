"""Deterministic Migration Risk Assessor.

Evaluates workflow complexity, security permissions, third-party actions,
infrastructure impact, and secrets posture to assign an explainable,
quantitative risk score (0-100) and severity rating (LOW, MEDIUM, HIGH, CRITICAL).
"""

from __future__ import annotations

from models.github_workflow import GitHubWorkflow
from models.migration_report import (
    ActionMappingResult,
    ActionMappingStatus,
    TerraformAnalysisResult,
)
from models.risk_model import (
    RiskAssessment,
    RiskCategory,
    RiskItem,
    RiskLevel,
)
from tools.github_parser import detect_hardcoded_credentials


def assess_migration_risk(
    workflow: GitHubWorkflow,
    action_mappings: list[ActionMappingResult],
    tf_result: TerraformAnalysisResult | None = None,
    raw_content: str = "",
) -> RiskAssessment:
    """Computes a deterministic, explainable risk assessment for the workflow migration."""
    items: list[RiskItem] = []
    blockers: list[str] = []
    cumulative_score = 0

    # 1. Action compatibility risks
    for m in action_mappings:
        if m.status == ActionMappingStatus.UNSUPPORTED:
            score = 25
            cumulative_score += score
            item = RiskItem(
                id=f"RISK-UNSUPPORTED-{m.action_name}",
                title=f"Unsupported Action: {m.action_name}",
                description=f"Action '{m.action_name}' cannot be translated to Azure DevOps native tasks.",
                level=RiskLevel.CRITICAL,
                score_impact=score,
                category=RiskCategory.COMPATIBILITY,
                remediation=m.manual_steps[0]
                if m.manual_steps
                else "Replace with supported Azure DevOps task.",
                component=m.action_name,
                blocker=True,
            )
            items.append(item)
            blockers.append(f"Unsupported action: {m.action_name}")

        elif m.status == ActionMappingStatus.UNKNOWN:
            score = 15
            cumulative_score += score
            item = RiskItem(
                id=f"RISK-UNKNOWN-{m.action_name}",
                title=f"Unrecognized Third-Party Action: {m.action_name}",
                description=f"Custom/third-party action '{m.action_name}' is not in the migration catalog.",
                level=RiskLevel.MEDIUM,
                score_impact=score,
                category=RiskCategory.COMPATIBILITY,
                remediation=f"Inspect implementation of '{m.action_name}' and replace with equivalent script or extension.",
                component=m.action_name,
            )
            items.append(item)

        elif m.status == ActionMappingStatus.MANUAL_MIGRATION:
            score = 15
            cumulative_score += score
            item = RiskItem(
                id=f"RISK-MANUAL-{m.action_name}",
                title=f"Manual Migration Required: {m.action_name}",
                description=f"Action '{m.action_name}' involves environment-specific SDK or context calls.",
                level=RiskLevel.MEDIUM,
                score_impact=score,
                category=RiskCategory.COMPATIBILITY,
                remediation="Rewrite script logic using Azure DevOps REST API or Azure CLI.",
                component=m.action_name,
            )
            items.append(item)

        elif m.status == ActionMappingStatus.PARTIAL:
            score = 5
            cumulative_score += score
            item = RiskItem(
                id=f"RISK-PARTIAL-{m.action_name}",
                title=f"Partial Action Mapping: {m.action_name}",
                description=f"Action '{m.action_name}' mapped with warnings or service connection prerequisites.",
                level=RiskLevel.LOW,
                score_impact=score,
                category=RiskCategory.COMPATIBILITY,
                remediation="; ".join(m.warnings) or "Verify inputs in generated pipeline.",
                component=m.action_name,
            )
            items.append(item)

    # 2. Permissions risks
    perms = workflow.permissions
    if perms == "write-all" or (isinstance(perms, dict) and perms.get("actions") == "write"):
        score = 20
        cumulative_score += score
        items.append(
            RiskItem(
                id="RISK-PERM-ELEVATED",
                title="Elevated Workflow Permissions (write-all)",
                description="Workflow grants broad write permissions. Azure DevOps pipelines run under the Project Collection Build Service by default.",
                level=RiskLevel.HIGH,
                score_impact=score,
                category=RiskCategory.SECURITY,
                remediation="Restrict Azure DevOps pipeline service connection and build service permissions to least-privilege.",
                component="permissions",
            )
        )

    # 3. Secret and credential risks
    if raw_content:
        hardcoded = detect_hardcoded_credentials(raw_content)
        if hardcoded:
            score = 35
            cumulative_score += score
            items.append(
                RiskItem(
                    id="RISK-SEC-HARDCODED",
                    title="Potential Hardcoded Secret Detected",
                    description="Static scanning detected high-entropy token or private key string literal in workflow.",
                    level=RiskLevel.CRITICAL,
                    score_impact=score,
                    category=RiskCategory.SECURITY,
                    remediation="Immediately revoke token, purge from git history, and rotate to Azure Key Vault.",
                    component="secrets",
                    blocker=True,
                )
            )
            blockers.append("Hardcoded secret pattern detected in workflow file.")

    if workflow.detected_secrets:
        sec_count = len(workflow.detected_secrets)
        score = min(sec_count * 3, 15)
        cumulative_score += score
        items.append(
            RiskItem(
                id="RISK-SEC-SECRETS-USED",
                title=f"{sec_count} Workflow Secret(s) Referenced",
                description=f"Workflow references: {', '.join(workflow.detected_secrets)}. These must be provisioned in Azure DevOps.",
                level=RiskLevel.LOW if sec_count <= 2 else RiskLevel.MEDIUM,
                score_impact=score,
                category=RiskCategory.SECURITY,
                remediation="Configure Azure DevOps Variable Group linked to Azure Key Vault for all secret references.",
                component="secrets",
            )
        )

    # 4. Terraform / Infrastructure risks
    if tf_result and tf_result.has_terraform:
        if not tf_result.backend_type:
            score = 15
            cumulative_score += score
            items.append(
                RiskItem(
                    id="RISK-TF-NO-BACKEND",
                    title="Terraform Missing Remote Backend",
                    description="No remote backend (azurerm, s3, etc.) configured in Terraform. State will be lost between CI runs.",
                    level=RiskLevel.HIGH,
                    score_impact=score,
                    category=RiskCategory.INFRASTRUCTURE,
                    remediation="Add 'backend \"azurerm\"' block to store state in an Azure Storage Account container with blob lease locking.",
                    component="terraform",
                )
            )
        if tf_result.service_connections_needed:
            items.append(
                RiskItem(
                    id="RISK-TF-SERVICE-CONNS",
                    title="Cloud Service Connection Prerequisites",
                    description=f"Terraform requires cloud provider credentials: {', '.join(tf_result.service_connections_needed)}.",
                    level=RiskLevel.MEDIUM,
                    score_impact=10,
                    category=RiskCategory.INFRASTRUCTURE,
                    remediation="Establish Workload Identity Federation (WIF) or Service Principal Service Connections in Azure DevOps.",
                    component="terraform",
                )
            )
            cumulative_score += 10

    # 5. Normalize overall score
    final_score = min(max(cumulative_score, 0), 100)

    if final_score >= 75 or len(blockers) > 0:
        overall_level = RiskLevel.CRITICAL
    elif final_score >= 50:
        overall_level = RiskLevel.HIGH
    elif final_score >= 25:
        overall_level = RiskLevel.MEDIUM
    else:
        overall_level = RiskLevel.LOW

    summary_text = (
        f"Migration evaluated with overall risk score {final_score}/100 ({overall_level.value}). "
        f"Identified {len(items)} risk factors with {len(blockers)} deployment blocker(s)."
    )

    return RiskAssessment(
        overall_score=final_score,
        overall_level=overall_level,
        items=items,
        summary=summary_text,
        blockers=blockers,
    )
