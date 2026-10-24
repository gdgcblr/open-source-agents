"""Cross-workflow correlation between pre-deployment code review and production incidents."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from agentrelay.schemas import CorrelationLink, CorrelationReport, InvestigationReport


def correlate_review_and_incident(
    review_report: InvestigationReport | Dict[str, Any],
    incident_data: Dict[str, Any],
) -> CorrelationReport:
    """Correlate pre-deployment code review findings with post-deployment incident data.

    Matches exact identifiers (commit SHA, deployment ID, service name).
    CRITICAL: A match establishes an association, NOT proof of causation.
    """
    if isinstance(review_report, InvestigationReport):
        review_dict = review_report.to_dict()
    else:
        review_dict = review_report

    correlations: List[CorrelationLink] = []
    unlinked_review_findings: List[str] = []
    unlinked_incident_events: List[str] = []

    # Extract review metadata
    review_meta = review_dict.get("execution_metadata", {})
    review_commit = review_meta.get("commit_id")
    review_service = review_meta.get("service")
    review_findings = review_dict.get("findings", [])

    # Extract incident data
    incident_id = str(incident_data.get("incident_id", "UNKNOWN"))
    incident_service = incident_data.get("service")
    incident_deployments = incident_data.get("deployments", [])
    incident_logs = incident_data.get("logs", [])

    # Incident events for linking
    incident_event_ids: List[str] = []
    for l in incident_logs:
        if str(l.get("level", "")).upper() in ("ERROR", "FATAL"):
            incident_event_ids.append(str(l.get("id", f"log-{l.get('message', '')[:20]}")))

    if not incident_event_ids and incident_deployments:
        incident_event_ids = [str(d.get("deployment_id", "dep-unknown")) for d in incident_deployments]

    # Collect all commits deployed in this incident
    deployed_commits = {}
    for dep in incident_deployments:
        cid = dep.get("commit_id")
        did = dep.get("deployment_id")
        dsrv = dep.get("service", incident_service)
        if cid:
            deployed_commits[cid] = (did, dsrv, dep.get("timestamp"))

    # Evaluate each review finding
    for finding in review_findings:
        claim = finding.get("claim", "Review finding")

        # Check 1: Missing identifiers
        if not review_commit and not deployed_commits:
            unlinked_review_findings.append(claim)
            continue

        # Check 2: Exact commit match
        if review_commit and review_commit in deployed_commits:
            dep_id, dep_srv, dep_ts = deployed_commits[review_commit]

            # Check for service conflict
            if review_service and dep_srv and review_service != dep_srv:
                # Conflicting service
                link = CorrelationLink(
                    relation_type="conflicting_service_match",
                    basis=(
                        f"Commit SHA '{review_commit}' matches deployment '{dep_id}', BUT services conflict: "
                        f"Review service was '{review_service}' while incident deployment was '{dep_srv}'."
                    ),
                    review_claim=claim,
                    incident_event_id=incident_id,
                    service=f"{review_service} vs {dep_srv}",
                    commit_id=review_commit,
                    deployment_id=dep_id,
                    is_causal_proof=False,
                    caution_note=(
                        "CONFLICTING EVIDENCE: Commit matches but service scopes differ. "
                        "Do not assume causality between unrelated service components."
                    ),
                )
                correlations.append(link)
            else:
                link = CorrelationLink(
                    relation_type="exact_commit_match",
                    basis=(
                        f"Code review commit SHA '{review_commit}' exactly matches deployment '{dep_id}' "
                        f"deployed to service '{dep_srv}'."
                    ),
                    review_claim=claim,
                    incident_event_id=incident_id,
                    service=dep_srv,
                    commit_id=review_commit,
                    deployment_id=dep_id,
                    is_causal_proof=False,
                    caution_note=(
                        "ASSOCIATION ONLY: Matching commit SHA proves that this code was deployed, "
                        "NOT that this specific code change caused the incident."
                    ),
                )
                correlations.append(link)

        # Check 3: Service match without commit match
        elif review_service and incident_service and review_service == incident_service:
            link = CorrelationLink(
                relation_type="service_match_only",
                basis=(
                    f"Review and incident share service '{review_service}', but commit IDs do not match "
                    f"(review commit: '{review_commit}', deployed commits: {list(deployed_commits.keys())})."
                ),
                review_claim=claim,
                incident_event_id=incident_id,
                service=review_service,
                commit_id=review_commit,
                deployment_id=None,
                is_causal_proof=False,
                caution_note=(
                    "WEAK ASSOCIATION: Service overlap alone is insufficient to attribute incident "
                    "to this review artifact."
                ),
            )
            correlations.append(link)

        else:
            unlinked_review_findings.append(claim)

    if not correlations and review_findings:
        summary = (
            f"Correlation completed: No direct link found between review findings and incident {incident_id}. "
            f"Identifiers (commit SHA, service) do not overlap."
        )
    elif correlations:
        summary = (
            f"Correlation completed: Established {len(correlations)} association(s) between code review "
            f"and incident {incident_id}. (All associations are non-causal hypotheses requiring verification)."
        )
    else:
        summary = f"Correlation completed: No review findings to correlate with incident {incident_id}."

    return CorrelationReport(
        summary=summary,
        correlations=correlations,
        unlinked_review_findings=unlinked_review_findings,
        unlinked_incident_events=unlinked_incident_events,
    )
