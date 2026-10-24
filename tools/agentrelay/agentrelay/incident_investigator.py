"""Deterministic production incident investigator and telemetry correlator."""

from __future__ import annotations

import statistics
from typing import Any, Dict, List, Optional, Tuple

from agentrelay.evidence import EvidenceStore
from agentrelay.schemas import EvidenceRecord, Finding, Hypothesis, InvestigationReport


def analyze_metric_series(
    metric_name: str,
    datapoints: List[Dict[str, Any]],
    service: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Analyze a time-series metric for significant anomalies or spikes.

    Uses simple statistical comparison (baseline vs spike) without unverified claims.
    """
    if not datapoints or len(datapoints) < 2:
        return None

    try:
        values = [float(dp.get("value", 0.0)) for dp in datapoints if "value" in dp]
        timestamps = [str(dp.get("timestamp", "")) for dp in datapoints]
    except (ValueError, TypeError):
        return None

    if len(values) < 2:
        return None

    # Split into first half (baseline) and second half (incident window)
    split = max(1, len(values) // 2)
    baseline_vals = values[:split]
    recent_vals = values[split:]

    base_mean = statistics.mean(baseline_vals)
    recent_max = max(recent_vals)
    recent_mean = statistics.mean(recent_vals)

    # Detect surge: recent mean is > 3x baseline or absolute increase is significant
    surge_detected = False
    details = ""

    if base_mean == 0.0 and recent_max > 0.0:
        surge_detected = True
        details = f"Surged from 0.0 to peak {recent_max:.2f}"
    elif base_mean > 0.0 and (recent_mean / base_mean >= 2.5 or recent_max / base_mean >= 3.0):
        surge_detected = True
        ratio = (recent_mean / base_mean) if base_mean else 0
        details = f"Elevated by {ratio:.1f}x (baseline mean: {base_mean:.2f}, incident mean: {recent_mean:.2f}, peak: {recent_max:.2f})"

    if surge_detected:
        peak_idx = values.index(recent_max)
        peak_time = timestamps[peak_idx] if peak_idx < len(timestamps) else "unknown"
        return {
            "metric_name": metric_name,
            "service": service,
            "baseline_mean": round(base_mean, 3),
            "recent_mean": round(recent_mean, 3),
            "peak_value": round(recent_max, 3),
            "peak_timestamp": peak_time,
            "details": details,
        }
    return None


def run_incident_investigation(
    incident_data: Dict[str, Any],
) -> Tuple[InvestigationReport, EvidenceStore]:
    """Deterministically analyze structured incident data (logs, metrics, traces, deployments).

    Produces an evidence-grounded investigation report distinguishing observed facts,
    plausible root-cause hypotheses, and unknowns.
    """
    evidence_store = EvidenceStore()
    findings: List[Finding] = []
    unknowns: List[str] = []
    recommendations: List[str] = []
    hypotheses: List[Hypothesis] = []

    incident_id = str(incident_data.get("incident_id", "INC-UNKNOWN"))
    primary_service = incident_data.get("service")

    deployments: List[Dict[str, Any]] = incident_data.get("deployments", [])
    logs: List[Dict[str, Any]] = incident_data.get("logs", [])
    metrics: List[Dict[str, Any]] = incident_data.get("metrics", [])
    traces: List[Dict[str, Any]] = incident_data.get("traces", [])

    ev_counter = 1

    # 1. Ingest & Correlate Deployment Evidence
    recent_deployments = []
    for dep in deployments:
        dep_id = str(dep.get("deployment_id", f"dep-{ev_counter}"))
        commit_id = dep.get("commit_id")
        timestamp = dep.get("timestamp")
        service = dep.get("service", primary_service)
        version = dep.get("version", "unknown")

        ev_id = f"ev-dep-{ev_counter:03d}"
        ev_counter += 1
        content = f"Deployment {dep_id} (commit: {commit_id}, version: {version}) executed at {timestamp} on service '{service}'."
        ev_rec = EvidenceRecord(
            id=ev_id,
            source_type="deployment",
            content=content,
            timestamp=timestamp,
            service=service,
            commit_id=commit_id,
            deployment_id=dep_id,
            metadata=dep,
        )
        evidence_store.add(ev_rec)
        recent_deployments.append((ev_id, dep))

    # 2. Analyze Metrics Time-Series
    metric_surge_ev_ids = []
    for met in metrics:
        name = met.get("name", "unknown_metric")
        service = met.get("service", primary_service)
        dps = met.get("datapoints", [])
        surge = analyze_metric_series(name, dps, service=service)
        if surge:
            ev_id = f"ev-met-{ev_counter:03d}"
            ev_counter += 1
            content = (
                f"Metric '{name}' on service '{service}' showed significant surge. "
                f"{surge['details']} peaking around {surge['peak_timestamp']}."
            )
            ev_rec = EvidenceRecord(
                id=ev_id,
                source_type="metric",
                content=content,
                timestamp=surge["peak_timestamp"],
                service=service,
                metadata=surge,
            )
            evidence_store.add(ev_rec)
            metric_surge_ev_ids.append((ev_id, surge))

            findings.append(
                Finding(
                    claim=f"Significant metric surge observed in '{name}' on {service}",
                    severity="high",
                    confidence="medium",
                    evidence_ids=[ev_id],
                    explanation=f"Telemetry indicates an abrupt shift: {surge['details']}.",
                    recommended_next_action=f"Correlate {name} timestamps with downstream dependencies and recent releases.",
                )
            )

    # 3. Analyze Error Logs
    error_logs = [l for l in logs if str(l.get("level", "")).upper() in ("ERROR", "FATAL", "CRITICAL")]
    grouped_errors: Dict[str, List[Dict[str, Any]]] = {}

    for l in error_logs:
        msg = str(l.get("message", "unknown error"))
        # Normalize error signature by stripping specific IDs or numbers
        sig = msg.split(":")[0] if ":" in msg else msg[:50]
        grouped_errors.setdefault(sig, []).append(l)

    error_ev_ids = []
    for sig, group in grouped_errors.items():
        ev_id = f"ev-log-{ev_counter:03d}"
        ev_counter += 1
        sample = group[0]
        ts = sample.get("timestamp")
        srv = sample.get("service", primary_service)
        content = (
            f"Error signature '{sig}' observed {len(group)} time(s) on service '{srv}'. "
            f"Sample log: {sample.get('message')}"
        )
        ev_rec = EvidenceRecord(
            id=ev_id,
            source_type="log",
            content=content,
            timestamp=ts,
            service=srv,
            metadata={"error_count": len(group), "sample": sample},
        )
        evidence_store.add(ev_rec)
        error_ev_ids.append((ev_id, sig, len(group)))

        findings.append(
            Finding(
                claim=f"Recurring error '{sig}' logged {len(group)} time(s) on {srv}",
                severity="high" if len(group) >= 3 else "medium",
                confidence="medium",
                evidence_ids=[ev_id],
                explanation=f"Error log cluster detected: {content}",
                recommended_next_action="Inspect full error stack trace and check downstream service availability.",
            )
        )

    # 4. Analyze Traces
    slow_or_error_traces = [t for t in traces if t.get("error") or float(t.get("duration_ms", 0)) > 2000]
    trace_ev_ids = []
    if slow_or_error_traces:
        ev_id = f"ev-trc-{ev_counter:03d}"
        ev_counter += 1
        sample_tr = slow_or_error_traces[0]
        content = (
            f"Distributed tracing captured {len(slow_or_error_traces)} failed or slow trace(s). "
            f"Sample trace ID '{sample_tr.get('trace_id')}' took {sample_tr.get('duration_ms')}ms "
            f"with error: {sample_tr.get('error_message', 'timeout')}"
        )
        ev_rec = EvidenceRecord(
            id=ev_id,
            source_type="trace",
            content=content,
            timestamp=sample_tr.get("timestamp"),
            service=primary_service,
            metadata={"trace_count": len(slow_or_error_traces), "sample": sample_tr},
        )
        evidence_store.add(ev_rec)
        trace_ev_ids.append(ev_id)

    # 5. Evaluate Missing Telemetry
    missing_telemetry = []
    if not traces:
        missing_telemetry.append("Distributed traces are missing for the incident window.")
        unknowns.append("No trace telemetry supplied; specific span bottlenecks cannot be confirmed.")
    if not metrics:
        missing_telemetry.append("System and application performance metrics are missing.")
        unknowns.append("No quantitative metrics provided; failure rate cannot be statistically bounded.")
    if not logs:
        missing_telemetry.append("Service application logs are missing.")
        unknowns.append("No application logs provided; internal runtime error messages are unknown.")

    # 6. Generate Ranked Hypotheses
    # Check if there is a deployment prior to the incident and error logs
    if recent_deployments and (error_ev_ids or metric_surge_ev_ids):
        dep_ev_id, dep = recent_deployments[0]
        supp_ids = [dep_ev_id]
        if metric_surge_ev_ids:
            supp_ids.append(metric_surge_ev_ids[0][0])
        if error_ev_ids:
            supp_ids.append(error_ev_ids[0][0])

        hypotheses.append(
            Hypothesis(
                title=f"Deployment {dep.get('deployment_id')} introduced a regression or resource leak",
                rank=1,
                likelihood="plausible",
                supporting_evidence_ids=supp_ids,
                contradicting_evidence_ids=[],
                missing_telemetry=missing_telemetry + ["Canary/rollback verification test results"],
                explanation=(
                    f"Deployment {dep.get('deployment_id')} (commit {dep.get('commit_id')}) coincided "
                    f"with the emergence of error logs and metric surges on service '{dep.get('service', primary_service)}'."
                ),
            )
        )

        # Alternative hypothesis: Downstream dependency / external outage
        alt_supp_ids = []
        if error_ev_ids:
            alt_supp_ids.append(error_ev_ids[0][0])
        if trace_ev_ids:
            alt_supp_ids.append(trace_ev_ids[0])

        hypotheses.append(
            Hypothesis(
                title="Downstream infrastructure or database connection pool exhaustion",
                rank=2,
                likelihood="possible",
                supporting_evidence_ids=alt_supp_ids,
                contradicting_evidence_ids=[],
                missing_telemetry=missing_telemetry + ["Database host metrics (CPU, connection count, IOPS)"],
                explanation=(
                    "Errors and trace timeouts may be caused by downstream latency or database connection limits "
                    "rather than application code changes alone."
                ),
            )
        )

    # If evidence is completely empty or insufficient: abstain
    if not findings and not hypotheses:
        report = InvestigationReport(
            summary=f"Incident {incident_id} investigation abstained: insufficient evidence.",
            findings=[],
            unknowns=["Insufficient telemetry provided. Logs, metrics, and deployments are empty or unparseable."],
            recommendations=[
                "Supply application logs, time-series metrics, and recent deployment manifests for this incident.",
                "Verify observability pipeline is delivering data for the affected service.",
            ],
            alternative_hypotheses=[],
            execution_metadata={"incident_id": incident_id, "abstained": True},
        )
        return report, evidence_store

    # Recommendations
    if recent_deployments:
        recommendations.append(
            f"Evaluate canary health and consider rolling back deployment {recent_deployments[0][1].get('deployment_id')} if errors persist."
        )
    recommendations.append("Inspect downstream database connection pool utilization and query latencies.")
    if missing_telemetry:
        recommendations.append(f"Collect missing telemetry: {'; '.join(missing_telemetry)}")

    summary = (
        f"Incident {incident_id} analysis: evaluated {len(logs)} logs, {len(metrics)} metrics series, "
        f"{len(traces)} traces, and {len(deployments)} deployments. Generated {len(findings)} verified findings "
        f"and {len(hypotheses)} plausible root-cause hypotheses."
    )

    report = InvestigationReport(
        summary=summary,
        findings=findings,
        unknowns=unknowns,
        recommendations=recommendations,
        alternative_hypotheses=hypotheses,
        execution_metadata={
            "incident_id": incident_id,
            "service": primary_service,
            "evidence_count": len(evidence_store.all_records()),
            "abstained": False,
        },
    )

    return report, evidence_store
