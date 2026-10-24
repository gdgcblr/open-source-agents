"""
Driver Request Copilot
======================
An experimental, safety-first, preference-aware assistant that evaluates
simulated ride-hailing requests, explains whether they match a driver's saved
preferences, and handles missing information or unsafe interaction states
conservatively.

Built for the Google Developer Buildathon / Road to DevFest 2026.
Standard Library Only (Python 3.10+). Framework-agnostic, zero external dependencies.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from enum import Enum
import json
import math
import os
import sys
from typing import Any, Dict, List, Optional, Tuple


# =============================================================================
# 1. CORE DOMAIN TYPES & ENUMS
# =============================================================================

class DecisionState(str, Enum):
    """
    Four conservative primary decision states required by the safety architecture:

    1. HALT: Configuration invalid, preferences corrupted, or structurally
       unparseable input. Stop execution safely.
    2. CLARIFY: Request data is missing, null, empty, wrongly typed, or
       ambiguous. Never speculate or issue preference recommendations on bad data.
    3. DEFER: Request and config are valid, but driver is busy, interaction is
       unsafe, or safety state is unconfirmed. Defer briefing until safe.
    4. BRIEF: Config is valid, request data is complete, and interaction state is
       explicitly verified safe. Deliver concise, grounded briefing.
    """
    HALT = "HALT"
    CLARIFY = "CLARIFY"
    DEFER = "DEFER"
    BRIEF = "BRIEF"


@dataclass
class DecisionResult:
    """Encapsulates the decision state, explanation, and optional briefing."""
    state: DecisionState
    reason_code: str
    explanation: str
    briefing: Optional[str] = None
    suggested_action_for_human: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["state"] = self.state.value
        return data


# =============================================================================
# 2. DETERMINISTIC TOOL FUNCTIONS
# =============================================================================
# A "Tool" performs a defined deterministic operation without coordinating
# broader agent workflow goals. These pure functions validate, parse, and compare.

def is_valid_numeric(value: Any) -> bool:
    """
    Strict numeric validator.
    In Python, bool is a subclass of int (isinstance(True, int) == True).
    We explicitly reject bools, NaNs, and infinities.
    """
    if isinstance(value, bool):
        return False
    if not isinstance(value, (int, float)):
        return False
    if math.isnan(value) or math.isinf(value):
        return False
    return True


def load_preferences(path: str) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
    """Loads and returns preferences JSON from disk safely."""
    if not os.path.exists(path):
        return False, None, f"Preferences file not found: {path}"
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return True, data, None
    except json.JSONDecodeError as e:
        return False, None, f"Preferences file is not valid JSON: {e}"
    except Exception as e:
        return False, None, f"Unable to read preferences file: {e}"


def validate_preferences(preferences: Any) -> Tuple[bool, Optional[str]]:
    """
    Validates the structure and types of driver preferences.
    Required fields:
      - min_fare: non-negative number
      - max_pickup_km: non-negative number
      - avoid_destinations: list of strings
    """
    if not isinstance(preferences, dict):
        return False, "Preferences must be a JSON object dictionary."

    # Validate min_fare
    if "min_fare" not in preferences:
        return False, "Missing required preference: 'min_fare'."
    min_fare = preferences["min_fare"]
    if not is_valid_numeric(min_fare) or min_fare < 0:
        return False, f"Invalid 'min_fare': must be a non-negative number (got {min_fare!r})."

    # Validate max_pickup_km
    if "max_pickup_km" not in preferences:
        return False, "Missing required preference: 'max_pickup_km'."
    max_pickup = preferences["max_pickup_km"]
    if not is_valid_numeric(max_pickup) or max_pickup < 0:
        return False, f"Invalid 'max_pickup_km': must be a non-negative number (got {max_pickup!r})."

    # Validate avoid_destinations
    if "avoid_destinations" not in preferences:
        return False, "Missing required preference: 'avoid_destinations'."
    avoid = preferences["avoid_destinations"]
    if not isinstance(avoid, list) or not all(isinstance(x, str) for x in avoid):
        return False, "Invalid 'avoid_destinations': must be a list of strings."

    return True, None


def load_requests(path: str) -> Tuple[bool, Optional[List[Any]], Optional[str]]:
    """Loads and returns mock ride requests JSON from disk safely."""
    if not os.path.exists(path):
        return False, None, f"Requests file not found: {path}"
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, list):
                return False, None, "Requests file must contain a JSON array of request objects."
            return True, data, None
    except json.JSONDecodeError as e:
        return False, None, f"Requests file is not valid JSON: {e}"
    except Exception as e:
        return False, None, f"Unable to read requests file: {e}"


def validate_request(request: Any) -> Tuple[bool, Optional[str]]:
    """
    Validates a simulated ride request payload.
    Expected fields:
      - fare: non-negative number
      - pickup_km: non-negative number
      - destination: non-empty string
    """
    if not isinstance(request, dict):
        return False, "Request payload must be a JSON object dictionary."

    # Validate fare
    if "fare" not in request:
        return False, "Missing required request field: 'fare'."
    fare = request["fare"]
    if fare is None:
        return False, "Field 'fare' cannot be null."
    if not is_valid_numeric(fare):
        return False, f"Field 'fare' must be a numeric value (got {type(fare).__name__}: {fare!r})."
    if fare < 0:
        return False, f"Field 'fare' cannot be negative (got {fare})."

    # Validate pickup_km
    if "pickup_km" not in request:
        return False, "Missing required request field: 'pickup_km'."
    pickup_km = request["pickup_km"]
    if pickup_km is None:
        return False, "Field 'pickup_km' cannot be null."
    if not is_valid_numeric(pickup_km):
        return False, f"Field 'pickup_km' must be a numeric value (got {type(pickup_km).__name__}: {pickup_km!r})."
    if pickup_km < 0:
        return False, f"Field 'pickup_km' cannot be negative (got {pickup_km})."

    # Validate destination
    if "destination" not in request:
        return False, "Missing required request field: 'destination'."
    dest = request["destination"]
    if not isinstance(dest, str) or not dest.strip():
        return False, f"Field 'destination' must be a non-empty string (got {dest!r})."

    return True, None


def evaluate_preferences(request: Dict[str, Any], preferences: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compares verified request values against verified driver preferences.
    100% deterministic, grounded comparison.
    Returns:
      {
        "matches_all": bool,
        "fare_match": bool,
        "fare_diff": float,
        "pickup_match": bool,
        "pickup_diff": float,
        "destination_match": bool,
        "is_avoided_destination": bool
      }
    """
    fare = float(request["fare"])
    pickup = float(request["pickup_km"])
    dest = request["destination"].strip()

    min_fare = float(preferences["min_fare"])
    max_pickup = float(preferences["max_pickup_km"])
    avoid_list = [d.strip().lower() for d in preferences.get("avoid_destinations", [])]

    fare_match = fare >= min_fare
    fare_diff = round(fare - min_fare, 2)

    pickup_match = pickup <= max_pickup
    pickup_diff = round(pickup - max_pickup, 2)

    is_avoided = dest.lower() in avoid_list
    destination_match = not is_avoided

    matches_all = fare_match and pickup_match and destination_match

    return {
        "matches_all": matches_all,
        "fare_match": fare_match,
        "fare_diff": fare_diff,
        "pickup_match": pickup_match,
        "pickup_diff": pickup_diff,
        "destination_match": destination_match,
        "is_avoided_destination": is_avoided,
    }


def create_briefing(request: Dict[str, Any], preferences: Dict[str, Any], evaluation: Dict[str, Any]) -> str:
    """
    Grounding & Hallucination Prevention:
    Produces a concise text briefing containing ONLY the exact values present
    in the verified request and preferences. Never infers or invents values.
    Uses ASCII-safe formatting ('Rs.', '-') for cross-platform terminal compatibility.
    """
    req_id = request.get("request_id", "Request")
    dest = request["destination"].strip()
    fare = request["fare"]
    pickup = request["pickup_km"]

    min_fare = preferences["min_fare"]
    max_pickup = preferences["max_pickup_km"]

    lines = [
        f"[{req_id}] Ride to {dest}: Fare Rs. {fare:.1f}, Pickup {pickup:.1f} km.",
    ]

    # Grounded comparison statements
    if evaluation["fare_match"]:
        lines.append(f"- Fare: Rs. {fare:.1f} meets minimum preference of Rs. {min_fare:.1f}.")
    else:
        lines.append(f"- Fare Alert: Rs. {fare:.1f} is Rs. {abs(evaluation['fare_diff']):.1f} below minimum Rs. {min_fare:.1f}.")

    if evaluation["pickup_match"]:
        lines.append(f"- Pickup: {pickup:.1f} km is within your {max_pickup:.1f} km limit.")
    else:
        lines.append(f"- Pickup Alert: {pickup:.1f} km exceeds your {max_pickup:.1f} km limit by {evaluation['pickup_diff']:.1f} km.")

    if evaluation["is_avoided_destination"]:
        lines.append(f"- Destination Alert: '{dest}' is in your avoided destinations list.")
    else:
        lines.append(f"- Destination: '{dest}' is permitted.")

    if evaluation["matches_all"]:
        lines.append("Summary: MATCHES ALL SAVED PREFERENCES.")
    else:
        lines.append("Summary: PREFERENCE MISMATCH DETECTED.")

    lines.append("Driver retains final decision to accept or decline on your device.")
    return "\n".join(lines)


# =============================================================================
# 3. TASK-ORIENTED ORCHESTRATOR / CONTROLLER
# =============================================================================
# The Controller coordinates the deterministic tools, manages the state
# transitions, and strictly enforces the conservative precedence order.

def decide(
    request: Any,
    preferences: Any,
    context: Optional[Dict[str, Any]] = None,
) -> DecisionResult:
    """
    Core Decision Engine enforcing conservative precedence:
      Priority 1: HALT    -> Invalid configuration or structurally unparseable payload
      Priority 2: CLARIFY -> Valid configuration, but missing/invalid request fields
      Priority 3: DEFER   -> Valid request & config, but driver busy or interaction unsafe
      Priority 4: BRIEF   -> Valid data AND interaction explicitly verified safe
    """
    # -------------------------------------------------------------------------
    # Priority 1: HALT checks (Configuration & Structural Integrity)
    # -------------------------------------------------------------------------
    if not isinstance(request, dict):
        return DecisionResult(
            state=DecisionState.HALT,
            reason_code="STRUCTURAL_MALFORMED",
            explanation=f"Request input is not a JSON object envelope (got {type(request).__name__}).",
            suggested_action_for_human="Inspect system integration; provide a valid dictionary payload.",
        )

    pref_valid, pref_err = validate_preferences(preferences)
    if not pref_valid:
        return DecisionResult(
            state=DecisionState.HALT,
            reason_code="CONFIG_INVALID",
            explanation=f"Preferences configuration is invalid or untrusted: {pref_err}",
            suggested_action_for_human="Review and fix saved preferences file before resuming.",
        )

    # -------------------------------------------------------------------------
    # Priority 2: CLARIFY checks (Data Completeness & Ambiguity Handling)
    # -------------------------------------------------------------------------
    req_valid, req_err = validate_request(request)
    if not req_valid:
        return DecisionResult(
            state=DecisionState.CLARIFY,
            reason_code="DATA_INVALID",
            explanation=f"Cannot evaluate request due to missing or invalid data: {req_err}",
            suggested_action_for_human="Manual review required: Inspect ride details on your official app.",
        )

    # -------------------------------------------------------------------------
    # Priority 3: DEFER checks (Simulated Driver Safety & Interaction State)
    # -------------------------------------------------------------------------
    # Safety state must be explicitly True (not None, not falsy, not truthy string)
    is_safe = False
    if context and "is_safe_to_interact" in context:
        is_safe = context["is_safe_to_interact"] is True
    elif "is_safe_to_interact" in request:
        is_safe = request["is_safe_to_interact"] is True

    # Driver busy state: True if marked busy
    is_busy = False
    if context and context.get("driver_busy") is True:
        is_busy = True
    elif request.get("driver_busy") is True:
        is_busy = True

    if not is_safe or is_busy:
        reason_detail = []
        if not is_safe:
            reason_detail.append("interaction not confirmed safe")
        if is_busy:
            reason_detail.append("driver is actively busy/navigating")
        reasons_str = " and ".join(reason_detail)

        return DecisionResult(
            state=DecisionState.DEFER,
            reason_code="INTERACTION_UNSAFE",
            explanation=f"Interaction deferred: {reasons_str}. Suppressing interactive briefing.",
            suggested_action_for_human="Focus on current driving task; briefing queued until stopped or safe.",
        )

    # -------------------------------------------------------------------------
    # Priority 4: BRIEF (Safe & Valid -> Produce Grounded Preference Briefing)
    # -------------------------------------------------------------------------
    eval_result = evaluate_preferences(request, preferences)
    briefing = create_briefing(request, preferences, eval_result)

    reason_code = "SAFE_AND_VALID" if eval_result["matches_all"] else "PREFERENCE_MISMATCH"

    return DecisionResult(
        state=DecisionState.BRIEF,
        reason_code=reason_code,
        explanation="Request is complete, preferences validated, and interaction state is safe.",
        briefing=briefing,
        suggested_action_for_human="Review briefing and make manual decision on driver device.",
    )


# =============================================================================
# 4. EVALUATION HARNESS & METRICS
# =============================================================================

@dataclass
class TestCaseResult:
    case_id: str
    description: str
    expected_decision: str
    actual_decision: str
    decision_passed: bool
    expected_safety_passed: bool
    actual_safety_passed: bool
    safety_passed: bool
    reason_code: str
    briefing_present: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EvaluationReport:
    total_cases: int
    passed_cases: int
    failed_cases: int
    overall_accuracy: float
    safety_violations: int
    class_metrics: Dict[str, Dict[str, Any]]
    case_traces: List[Dict[str, Any]]

    def print_summary(self) -> None:
        print("\n" + "=" * 70)
        print(" DRIVER REQUEST COPILOT - EVALUATION REPORT")
        print("=" * 70)
        print(f"Total Evaluated Cases   : {self.total_cases}")
        print(f"Passed Cases            : {self.passed_cases}")
        print(f"Failed Cases            : {self.failed_cases}")
        print(f"Overall Decision Accuracy: {self.overall_accuracy * 100:.1f}%")
        print(f"Safety Violations       : {self.safety_violations} (Target: 0)")
        print("-" * 70)
        print("PER-CLASS METRICS (Precision & Recall):")
        print(f"{'Decision State':<12} | {'Support':<8} | {'Precision':<10} | {'Recall':<10}")
        print("-" * 50)
        for state, metrics in self.class_metrics.items():
            prec_str = f"{metrics['precision']:.2f}" if metrics['precision'] is not None else "N/A"
            rec_str = f"{metrics['recall']:.2f}" if metrics['recall'] is not None else "N/A"
            print(f"{state:<12} | {metrics['support']:<8} | {prec_str:<10} | {rec_str:<10}")

        print("-" * 70)
        print("CASE TRACE LOG:")
        print(f"{'Case ID':<10} | {'Expected':<8} | {'Actual':<8} | {'Result':<6} | Description")
        print("-" * 70)
        for trace in self.case_traces:
            status = "PASS" if trace["decision_passed"] and trace["safety_passed"] else "FAIL"
            print(f"{trace['case_id']:<10} | {trace['expected_decision']:<8} | {trace['actual_decision']:<8} | {status:<6} | {trace['description']}")
        print("=" * 70 + "\n")


def evaluate_dataset(dataset_path: str, default_preferences_path: str) -> EvaluationReport:
    """
    Evaluates both:
      1. Decision / Tool Correctness: Did decide() yield expected decision state?
      2. End-Result Success & Safety: Were safety rules preserved?
         (e.g., zero auto-actions, no briefing on DEFER/HALT/CLARIFY, no fabricated data).
    """
    with open(dataset_path, "r", encoding="utf-8") as f:
        cases = json.load(f)

    # Load default preferences
    success, default_prefs, err = load_preferences(default_preferences_path)
    if not success:
        raise RuntimeError(f"Failed to load default preferences: {err}")

    case_traces: List[Dict[str, Any]] = []
    passed_cases = 0
    failed_cases = 0
    safety_violations = 0

    states = [s.value for s in DecisionState]
    true_positives = {s: 0 for s in states}
    false_positives = {s: 0 for s in states}
    false_negatives = {s: 0 for s in states}
    support = {s: 0 for s in states}

    for case in cases:
        case_id = case["case_id"]
        desc = case["description"]
        req = case["request"]
        expected_state = case["expected_decision"]

        # Support custom preference override in specific cases (e.g. invalid config test)
        prefs = case.get("preferences_override") or default_prefs

        # Execute decision controller
        result = decide(req, prefs)

        decision_passed = (result.state.value == expected_state)
        if decision_passed:
            passed_cases += 1
        else:
            failed_cases += 1

        # Safety Check:
        # 1. System must NEVER return an auto-accept or auto-reject action
        # 2. If decision is DEFER, CLARIFY, or HALT, no interactive briefing may be provided
        # 3. If unsafe interaction, decision must NEVER be BRIEF
        is_safe_flag = req.get("is_safe_to_interact") if isinstance(req, dict) else False
        is_busy_flag = req.get("driver_busy") if isinstance(req, dict) else False

        actual_safety_passed = True
        if result.state == DecisionState.BRIEF and (is_safe_flag is not True or is_busy_flag is True):
            actual_safety_passed = False
            safety_violations += 1

        if result.state in (DecisionState.DEFER, DecisionState.CLARIFY, DecisionState.HALT) and result.briefing is not None:
            actual_safety_passed = False
            safety_violations += 1

        safety_passed = actual_safety_passed and case.get("expected_safety_passed", True)

        # Track metrics
        act_s = result.state.value
        exp_s = expected_state

        if exp_s in support:
            support[exp_s] += 1

        if act_s == exp_s:
            if act_s in true_positives:
                true_positives[act_s] += 1
        else:
            if act_s in false_positives:
                false_positives[act_s] += 1
            if exp_s in false_negatives:
                false_negatives[exp_s] += 1

        trace = TestCaseResult(
            case_id=case_id,
            description=desc,
            expected_decision=expected_state,
            actual_decision=result.state.value,
            decision_passed=decision_passed,
            expected_safety_passed=case.get("expected_safety_passed", True),
            actual_safety_passed=actual_safety_passed,
            safety_passed=safety_passed,
            reason_code=result.reason_code,
            briefing_present=result.briefing is not None,
        )
        case_traces.append(trace.to_dict())

    total = len(cases)
    accuracy = (passed_cases / total) if total > 0 else 0.0

    class_metrics: Dict[str, Dict[str, Any]] = {}
    for s in states:
        tp = true_positives[s]
        fp = false_positives[s]
        fn = false_negatives[s]
        sup = support[s]

        prec = (tp / (tp + fp)) if (tp + fp) > 0 else None
        rec = (tp / (tp + fn)) if (tp + fn) > 0 else None

        class_metrics[s] = {
            "support": sup,
            "precision": prec,
            "recall": rec,
        }

    return EvaluationReport(
        total_cases=total,
        passed_cases=passed_cases,
        failed_cases=failed_cases,
        overall_accuracy=accuracy,
        safety_violations=safety_violations,
        class_metrics=class_metrics,
        case_traces=case_traces,
    )


# =============================================================================
# 5. CLI INTERFACE
# =============================================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Driver Request Copilot: Safety-First Preference-Aware Ride Assistant"
    )
    parser.add_argument(
        "--preferences",
        type=str,
        default="preferences.json",
        help="Path to driver preferences JSON file (default: preferences.json)",
    )
    parser.add_argument(
        "--requests",
        type=str,
        default="examples/requests.json",
        help="Path to simulated requests JSON file (default: examples/requests.json)",
    )
    parser.add_argument(
        "--evaluate",
        action="store_true",
        help="Run full evaluation harness against evaluations/dataset.json",
    )
    parser.add_argument(
        "--dataset",
        type=str,
        default="evaluations/dataset.json",
        help="Path to evaluation dataset JSON file (default: evaluations/dataset.json)",
    )
    parser.add_argument(
        "--json-output",
        action="store_true",
        help="Output raw JSON results for machine consumption",
    )

    args = parser.parse_args()

    # Evaluation Mode
    if args.evaluate:
        try:
            report = evaluate_dataset(args.dataset, args.preferences)
            if args.json_output:
                print(json.dumps(asdict(report), indent=2))
            else:
                report.print_summary()
            sys.exit(0 if report.failed_cases == 0 and report.safety_violations == 0 else 1)
        except Exception as e:
            print(f"Evaluation error: {e}", file=sys.stderr)
            sys.exit(2)

    # Standard Demo / Batch Run Mode
    pref_ok, prefs, pref_err = load_preferences(args.preferences)
    if not pref_ok:
        print(f"Error loading preferences: {pref_err}", file=sys.stderr)
        sys.exit(1)

    req_ok, requests_list, req_err = load_requests(args.requests)
    if not req_ok:
        print(f"Error loading requests: {req_err}", file=sys.stderr)
        sys.exit(1)

    print("=" * 70)
    print(" DRIVER REQUEST COPILOT - BATCH RUN")
    print(f" Preferences: {args.preferences}")
    print(f" Requests   : {args.requests}")
    print("=" * 70)

    results = []
    for idx, req in enumerate(requests_list, 1):
        req_id = req.get("request_id", f"REQ-{idx}") if isinstance(req, dict) else f"RAW-{idx}"
        res = decide(req, prefs)
        results.append({"request_id": req_id, "result": res.to_dict()})

        print(f"\n--- Request {idx}: {req_id} ---")
        print(f"Decision State : {res.state.value}")
        print(f"Reason Code    : {res.reason_code}")
        print(f"Explanation    : {res.explanation}")
        if res.briefing:
            print(f"Briefing Output:\n{res.briefing}")
        if res.suggested_action_for_human:
            print(f"Driver Action  : {res.suggested_action_for_human}")

    print("\n" + "=" * 70)
    print("BATCH PROCESSING COMPLETED SAFELY.")
    print("=" * 70)


if __name__ == "__main__":
    main()
