"""
Stakeholder Dispatch Sub-Agent
================================
Part of the KPI Drift RCA Agent multi-agent system.

Role:
  Once the primary RCA agent isolates the culprit cohort and generates
  technical hypotheses, this sub-agent maps findings into concrete,
  assigned incident action items for functional leads:
    - Engineering / DevOps Lead: Rollbacks, CDN/telemetry inspection, latency tracing.
    - Growth / Paid Media Lead: Bid caps, UTM audits, channel pacing, pixel verification.
    - Regional / Geography Manager: Payment gateway degradation, regional banking/ISP status.

Each action item includes:
  - Priority: P0 / P1 / P2
  - Assignee Role
  - Investigation SLA: (e.g., 2 hours for P0)
  - Trigger Finding
  - Investigation Focus
  - Expected Resolution Action
"""

import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _build_deterministic_fallback_actions(
    stats: Dict[str, Any],
    dimensions: List[str],
) -> List[Dict[str, Any]]:
    """
    Deterministic domain-driven action generator when LLM is offline.
    Uses exact mathematical facts from the isolated culprit cohort.
    """
    top_drag = stats["primary_negative_drivers"][0] if stats.get("primary_negative_drivers") else {}
    metric = stats.get("metric", "metric")
    total_delta = stats.get("absolute_delta", 0)
    pct_change = stats.get("percentage_change", 0.0)

    # Extract cohort dimensions
    country = str(top_drag.get("country", top_drag.get("region", "Global")))
    device = str(top_drag.get("device", "All Devices"))
    channel = str(top_drag.get("channel", "All Channels"))
    cohort_delta = top_drag.get("delta", total_delta)
    cohort_contrib = top_drag.get("pct_contribution", 100.0)

    # Determine severity based on percentage change and delta
    is_p0 = abs(pct_change) >= 20.0 or abs(cohort_contrib) >= 50.0
    p0_or_p1 = "P0" if is_p0 else "P1"
    devops_sla = "2 hours (Critical P0)" if is_p0 else "4 hours"
    growth_sla = "4 hours" if is_p0 else "8 hours"
    regional_sla = "4 hours" if is_p0 else "12 hours"

    actions = [
        {
            "priority": p0_or_p1,
            "assignee_role": "Engineering / DevOps Lead",
            "sla": devops_sla,
            "trigger_finding": (
                f"{country} / {device} / {channel} driving {cohort_delta:,.0f} {metric} drop "
                f"({cohort_contrib}% of total drift)"
            ),
            "investigation_focus": (
                f"Inspect edge CDN error rates, API gateway latency, and recent deployment commits "
                f"touching {device.lower()} clients for region {country}."
            ),
            "expected_resolution": (
                f"Revert recent client releases or hotfix offending service worker / checkout JS bundles. "
                f"Verify synthetic health checks for {country} endpoints."
            ),
        },
        {
            "priority": "P1",
            "assignee_role": "Growth / Paid Media Lead",
            "sla": growth_sla,
            "trigger_finding": (
                f"Disproportionate drop in {channel} acquisition volume and conversion efficiency."
            ),
            "investigation_focus": (
                f"Audit active ad campaigns on {channel} targeting {country} on {device}. "
                f"Verify landing page redirection parameters, UTM tagging, and attribution pixel firing."
            ),
            "expected_resolution": (
                f"Pause or reallocate underperforming campaign budgets. "
                f"Restore missing attribution parameters and verify conversion postback health."
            ),
        },
        {
            "priority": "P1" if country not in ("Global", "All") else "P2",
            "assignee_role": "Regional / Geography Manager",
            "sla": regional_sla,
            "trigger_finding": (
                f"Localized KPI deterioration concentrated within region: {country}."
            ),
            "investigation_focus": (
                f"Assess regional payment gateway authorization rates (e.g., 3D-Secure, local cards), "
                f"telecom/ISP routing issues, and local currency checkout services in {country}."
            ),
            "expected_resolution": (
                f"Switch traffic routing to secondary payment processor in {country} if authorization "
                f"rate has degraded. Post status page notification if localized banking outage confirmed."
            ),
        },
    ]

    return actions


def dispatch_stakeholder_actions(
    stats: Dict[str, Any],
    diagnosis: str,
    dimensions: List[str],
    client: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Sub-agent coordinator that maps technical RCA findings into actionable,
    role-assigned operational tickets with priorities and SLAs.
    """
    top_drag = stats["primary_negative_drivers"][0] if stats.get("primary_negative_drivers") else {}
    cohort_str = " / ".join(f"{d}={top_drag.get(d, '?')}" for d in dimensions)

    total_delta = stats.get("absolute_delta", 0)
    pct_change = stats.get("percentage_change", 0.0)
    severity = "SEV-1 (Critical)" if abs(pct_change) >= 20.0 else "SEV-2 (Major)"

    # If live Gemini client is available, prompt for tailored dynamic dispatch
    if client is not None:
        prompt = f"""You are the Stakeholder Action Dispatch Sub-Agent in an Enterprise Incident Management system.

Context:
Primary RCA Agent has isolated the metric drift root cause:
- Target Metric: {stats.get('metric')}
- Baseline Total: {stats.get('baseline_total')} -> Current Total: {stats.get('current_total')}
- Overall Drift: {total_delta} ({pct_change}%)
- Culprit Cohort: {cohort_str}
- Top Drag Delta: {top_drag.get('delta')} ({top_drag.get('pct_contribution')}% contribution)

Primary Diagnosis Summary:
{diagnosis[:1200]}

Your Task:
Map these findings into exactly 3 assigned incident response action items for:
1. Engineering / DevOps Lead
2. Growth / Paid Media Lead
3. Regional / Geography Manager

Requirements:
- Priority must be P0, P1, or P2 based on severity.
- Assignee Role must match the designated lead.
- SLA must be specific (e.g., '2 hours', '4 hours', '24 hours').
- Expected Resolution Action must be concrete and actionable.

Return ONLY a valid JSON array of 3 objects with these exact keys:
[
  {{
    "priority": "P0",
    "assignee_role": "Engineering / DevOps Lead",
    "sla": "2 hours",
    "trigger_finding": "...",
    "investigation_focus": "...",
    "expected_resolution": "..."
  }},
  ...
]
"""
        for model_id in ["gemini-2.5-flash", "gemini-3.5-flash-lite", "gemini-flash-latest"]:
            try:
                response = client.models.generate_content(
                    model=model_id,
                    contents=prompt,
                )
                text = getattr(response, "text", "")
                # Extract JSON array
                match = re.search(r"\[\s*\{.*\}\s*\]", text, re.DOTALL)
                if match:
                    parsed = json.loads(match.group(0))
                    if isinstance(parsed, list) and len(parsed) >= 3:
                        return {
                            "incident_severity": severity,
                            "dispatch_timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                            "culprit_cohort": cohort_str,
                            "actions": parsed,
                            "dispatcher_mode": f"Live Gemini Sub-Agent ({model_id})",
                        }
            except Exception:
                continue

    # Fallback to deterministic domain-rules generator
    actions = _build_deterministic_fallback_actions(stats, dimensions)
    return {
        "incident_severity": severity,
        "dispatch_timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "culprit_cohort": cohort_str,
        "actions": actions,
        "dispatcher_mode": "Deterministic Domain Rules Sub-Agent",
    }


def format_dispatch_terminal(dispatch: Dict[str, Any]) -> str:
    """Format the dispatch result as a clean terminal table."""
    lines = [
        "",
        "+------------------------------------------------------------------------------------+",
        "|             MULTI-AGENT STAKEHOLDER INCIDENT ACTION DISPATCH MATRIX                |",
        "+------------------------------------------------------------------------------------+",
        f"| Severity: {dispatch['incident_severity']:<16} Culprit: {dispatch['culprit_cohort']:<42} |",
        f"| Dispatcher: {dispatch['dispatcher_mode']:<70} |",
        "+------------------------------------------------------------------------------------+",
        "",
    ]

    for item in dispatch["actions"]:
        p_badge = f"[{item.get('priority', 'P1')}]"
        role = item.get("assignee_role", "Lead")
        sla = item.get("sla", "4 hours")
        lines.append(f"  {p_badge:<5} {role} (SLA: {sla})")
        lines.append(f"         Trigger  : {item.get('trigger_finding', 'N/A')}")
        lines.append(f"         Inspect  : {item.get('investigation_focus', 'N/A')}")
        lines.append(f"         Action   : {item.get('expected_resolution', 'N/A')}")
        lines.append("")

    return "\n".join(lines)


def format_dispatch_markdown(dispatch: Dict[str, Any]) -> str:
    """Format the dispatch result as a clean Markdown section for report.md."""
    lines = [
        "## Multi-Agent Stakeholder Incident Dispatch",
        "",
        f"> **Incident Severity**: `{dispatch['incident_severity']}`  ",
        f"> **Dispatched**: `{dispatch['dispatch_timestamp']}` via `{dispatch['dispatcher_mode']}`  ",
        f"> **Culprit Cohort Target**: `{dispatch['culprit_cohort']}`",
        "",
        "| Priority | Assignee Role | SLA | Immediate Investigation Focus | Expected Resolution Action |",
        "|:---|:---|:---|:---|:---|",
    ]

    for item in dispatch["actions"]:
        pri = f"**{item.get('priority', 'P1')}**"
        role = item.get("assignee_role", "")
        sla = item.get("sla", "")
        focus = item.get("investigation_focus", "").replace("|", "/")
        action = item.get("expected_resolution", "").replace("|", "/")
        lines.append(f"| {pri} | {role} | {sla} | {focus} | {action} |")

    lines.append("")
    return "\n".join(lines)
