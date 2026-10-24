"""AgentTrace - Deterministic trace analyzer.

Authoritative implementation of the Analyzer Logic Contract (v1).
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

TIMEOUT_INDICATORS = ("timeout", "timed out", "deadline exceeded", "request expired")

SEVERITY_ORDER = {
    "Critical": 0,
    "High": 1,
    "Medium": 2,
    "Info": 3,
}


def _bound_text(text: str, max_chars: int = 1000) -> str:
    """Bound string to max_chars characters."""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3] + "..."


def _normalize_id(val: Any) -> Optional[str]:
    """Normalize event or call id to a string if present."""
    if val is None:
        return None
    if isinstance(val, (str, int, float)):
        s = str(val).strip()
        return s if s else None
    return str(val)


def _normalize_input(val: Any) -> str:
    """Deterministic JSON normalization of tool inputs."""
    if val is None:
        return "null"
    try:
        return json.dumps(val, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    except (TypeError, ValueError):
        return _bound_text(str(val))


def _validate_root(trace: Any) -> None:
    """Validate root structure and raise ValueError on contract violations."""
    if not isinstance(trace, dict):
        raise ValueError("Trace root must be a JSON object (dictionary).")

    if "events" not in trace:
        raise ValueError("Trace must contain an 'events' array.")

    if not isinstance(trace["events"], list):
        raise ValueError("Trace 'events' must be an array (list).")

    if "name" in trace and not isinstance(trace["name"], str):
        raise ValueError("Trace 'name' must be a string if present.")

    if "complete" in trace and not isinstance(trace["complete"], bool):
        raise ValueError("Trace 'complete' must be a boolean if present.")


def analyze_trace(trace: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze an AI agent execution trace deterministically.

    Parameters:
        trace: Python dict conforming to AgentTrace schema.

    Returns:
        Dict with keys: trace_name, event_count, finding_count, findings, timeline.

    Raises:
        ValueError if the root structure or types violate the schema contract.
    """
    _validate_root(trace)

    raw_name = trace.get("name")
    trace_name = raw_name.strip() if isinstance(raw_name, str) and raw_name.strip() else "Untitled trace"
    is_complete = trace.get("complete") is True

    raw_events = trace["events"]
    event_count = len(raw_events)

    # Output timeline will be a shallow copy of event objects (preserving unknown fields)
    timeline: List[Any] = []

    findings: List[Dict[str, Any]] = []
    seq_counter = 0

    def add_finding(
        severity: str,
        title: str,
        evidence: str,
        recommendation: str,
        event_id: Optional[str] = None,
    ) -> None:
        nonlocal seq_counter
        findings.append({
            "severity": severity,
            "title": title,
            "evidence": _bound_text(evidence),
            "recommendation": recommendation,
            "event_id": event_id,
            "_seq": seq_counter,
        })
        seq_counter += 1

    seen_ids: Dict[str, int] = {}
    ambiguous_ids: set[str] = set()

    # Tool calls tracking: call_id -> (event_id, tool_name, raw_event)
    valid_tool_calls: Dict[str, Dict[str, Any]] = {}

    # Tool call groups for repeated call detection: (norm_tool, norm_input) -> metadata
    tool_call_groups: Dict[Tuple[str, str], Dict[str, Any]] = {}

    # Tool results tracking: set of call_ids referenced by tool_result/tool_output
    answered_call_ids: set[str] = set()

    for idx, raw_event in enumerate(raw_events):
        if not isinstance(raw_event, dict):
            timeline.append(raw_event)
            add_finding(
                severity="Medium",
                title="Malformed event entry",
                evidence=f"Event at array index {idx} is not an object: {_bound_text(str(raw_event))}",
                recommendation=f"Ensure event at index {idx} is a valid JSON object.",
                event_id=None,
            )
            continue

        # Keep a shallow copy in timeline to avoid input mutation
        event = dict(raw_event)
        timeline.append(event)

        # Normalize ID
        raw_id = event.get("id")
        norm_id = _normalize_id(raw_id)
        if norm_id is not None:
            if norm_id in seen_ids:
                ambiguous_ids.add(norm_id)
                add_finding(
                    severity="Medium",
                    title="Duplicate event identifier",
                    evidence=f"Event at index {idx} has duplicate id '{norm_id}' previously seen at index {seen_ids[norm_id]}.",
                    recommendation="Ensure all event IDs are globally unique across the trace.",
                    event_id=norm_id,
                )
            else:
                seen_ids[norm_id] = idx

        # Extract normalized event type
        raw_type = event.get("type")
        event_type = str(raw_type).strip().lower() if raw_type is not None else ""

        # 1. Explicit error event - Critical or High
        if event_type == "error":
            error_val = event.get("error")
            has_error_details = (
                error_val is not None
                and (bool(str(error_val).strip()) if isinstance(error_val, str) else bool(error_val))
            )
            if has_error_details:
                add_finding(
                    severity="Critical",
                    title="Explicit error event detected",
                    evidence=f"Error event at index {idx}: {_bound_text(str(error_val))}",
                    recommendation="Inspect the preceding event, tool input, and agent configuration to resolve the failure.",
                    event_id=norm_id,
                )
            else:
                add_finding(
                    severity="High",
                    title="Error event has no details",
                    evidence=f"Event at index {idx} has type 'error' but error field is missing or empty.",
                    recommendation="Ensure error events capture diagnostic details or stack traces.",
                    event_id=norm_id,
                )
        else:
            # 2. Error on another event - High
            error_val = event.get("error")
            has_error_details = (
                error_val is not None
                and (bool(str(error_val).strip()) if isinstance(error_val, str) else bool(error_val))
            )
            if has_error_details:
                display_type = event_type if event_type else "untyped event"
                add_finding(
                    severity="High",
                    title=f"Error reported on {display_type}",
                    evidence=f"Event at index {idx} ({display_type}) reported error: {_bound_text(str(error_val))}",
                    recommendation=f"Investigate the error reported on event {norm_id or f'at index {idx}'}.",
                    event_id=norm_id,
                )

        # Tool calls processing
        if event_type == "tool_call":
            if norm_id is None:
                add_finding(
                    severity="Medium",
                    title="Tool call missing identifier",
                    evidence=f"tool_call event at index {idx} has missing or empty id.",
                    recommendation="Provide a unique id for each tool_call to enable result matching.",
                    event_id=None,
                )
            else:
                valid_tool_calls[norm_id] = {
                    "event_id": norm_id,
                    "index": idx,
                    "tool": event.get("tool", "unknown"),
                    "raw_event": event,
                }

            # Grouping for repeated calls
            raw_tool = event.get("tool")
            tool_name_orig = str(raw_tool) if raw_tool is not None else "unknown"
            norm_tool = tool_name_orig.strip().lower()
            norm_input = _normalize_input(event.get("input"))
            group_key = (norm_tool, norm_input)

            if group_key not in tool_call_groups:
                tool_call_groups[group_key] = {
                    "tool_orig": tool_name_orig,
                    "norm_input": norm_input,
                    "call_ids": [norm_id] if norm_id else [f"index-{idx}"],
                    "count": 1,
                }
            else:
                group = tool_call_groups[group_key]
                group["count"] += 1
                if norm_id and norm_id not in group["call_ids"]:
                    group["call_ids"].append(norm_id)
                elif not norm_id:
                    group["call_ids"].append(f"index-{idx}")

        # Tool results processing
        if event_type in ("tool_result", "tool_output"):
            raw_call_id = event.get("call_id")
            norm_call_id = _normalize_id(raw_call_id)
            if norm_call_id is None:
                add_finding(
                    severity="Medium",
                    title="Tool result missing call_id",
                    evidence=f"Event at index {idx} ({event_type}) is missing a 'call_id' reference.",
                    recommendation="Specify a valid 'call_id' on tool results to link them to their tool call.",
                    event_id=norm_id,
                )
            else:
                answered_call_ids.add(norm_call_id)

            # 4. Timeout-like tool result - Medium (at most one per event)
            matched_timeout = None
            out_val = event.get("output")
            if isinstance(out_val, str):
                out_lower = out_val.lower()
                for ind in TIMEOUT_INDICATORS:
                    if ind in out_lower:
                        matched_timeout = f"output contains '{ind}': {_bound_text(out_val)}"
                        break

            if not matched_timeout:
                err_val = event.get("error")
                if isinstance(err_val, str):
                    err_lower = err_val.lower()
                    for ind in TIMEOUT_INDICATORS:
                        if ind in err_lower:
                            matched_timeout = f"error contains '{ind}': {_bound_text(err_val)}"
                            break

            if matched_timeout:
                add_finding(
                    severity="Medium",
                    title="Timeout-like tool execution detected",
                    evidence=f"Tool result at index {idx} shows timeout indication ({matched_timeout}).",
                    recommendation="Inspect tool responsiveness, network conditions, or increase timeout thresholds.",
                    event_id=norm_id,
                )

    # 3. Repeated identical tool calls - High
    for group in tool_call_groups.values():
        if group["count"] >= 3:
            rep_ids = group["call_ids"][:5]
            ids_str = ", ".join(rep_ids)
            if len(group["call_ids"]) > 5:
                ids_str += f" and {len(group['call_ids']) - 5} more"
            add_finding(
                severity="High",
                title=f"Repeated identical tool calls: {group['tool_orig']}",
                evidence=(
                    f"Tool '{group['tool_orig']}' called {group['count']} times with identical input: "
                    f"{_bound_text(group['norm_input'])}. Representative call IDs: [{ids_str}]."
                ),
                recommendation="Investigate why the agent repeated the identical call; consider adding loop detection or verifying tool responses.",
                event_id=group["call_ids"][0] if group["call_ids"] and not group["call_ids"][0].startswith("index-") else None,
            )

    # 5. Missing result - Medium (only if complete is exactly True)
    if is_complete:
        for call_id, call_info in valid_tool_calls.items():
            if call_id in ambiguous_ids:
                continue
            if call_id not in answered_call_ids:
                tool_name = call_info["tool"]
                add_finding(
                    severity="Medium",
                    title="Unmatched tool call with missing result",
                    evidence=f"Tool call '{tool_name}' with ID '{call_id}' has no matching tool_result or tool_output in completed trace.",
                    recommendation="Check if the agent terminated prematurely or if tool output was dropped.",
                    event_id=call_id,
                )

    # 7. No supported pattern
    if not findings:
        add_finding(
            severity="Info",
            title="No known failure pattern detected",
            evidence="All supported heuristic checks (malformed events, explicit errors, repeated calls, timeouts, and unmatched calls) passed without finding known failure patterns.",
            recommendation="No known issues detected under supported rules. Note that this does not guarantee overall task success.",
            event_id=None,
        )

    # Sort findings by severity then deterministic sequence order
    findings.sort(key=lambda f: (SEVERITY_ORDER.get(f["severity"], 99), f["_seq"]))
    for f in findings:
        del f["_seq"]

    return {
        "trace_name": trace_name,
        "event_count": event_count,
        "finding_count": len(findings),
        "findings": findings,
        "timeline": timeline,
    }
