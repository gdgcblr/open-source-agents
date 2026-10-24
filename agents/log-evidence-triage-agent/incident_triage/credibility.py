"""Closed claim vocabulary: a real citation alone cannot support arbitrary prose."""
from copy import deepcopy


def citations_valid(report: dict) -> bool:
    refs = [ref for claim in report["findings"] for ref in claim["evidence_refs"]]
    refs += report["escalation"]["evidence_refs"]
    return all(ref in report["evidence"] for ref in refs) and all(c["evidence_refs"] for c in report["findings"])


def validate_candidate(candidate: object, report: dict) -> bool:
    if not isinstance(candidate, dict) or set(candidate) != {"decision", "claims"}:
        return False
    if candidate["decision"] != report["decision"] or not isinstance(candidate["claims"], list) or not candidate["claims"]:
        return False
    allowed = {claim["id"]: claim for claim in report["findings"]}
    seen = set()
    for claim in candidate["claims"]:
        if not isinstance(claim, dict) or not isinstance(claim.get("id"), str):
            return False
        if claim["id"] in seen or claim != allowed.get(claim["id"]):
            return False
        seen.add(claim["id"])
    return citations_valid(report)


def apply_candidate(report: dict, candidate: object) -> dict:
    result = deepcopy(report)
    if validate_candidate(candidate, report):
        result["mode"] = "ai_assisted_validated"
        result["ai_selected_findings"] = [c["id"] for c in candidate["claims"]]
    else:
        result["mode"] = "offline_fallback"
        result["fallback_reason"] = "AI output failed the claim/evidence contract; deterministic findings retained."
        result["credibility"] = {"valid": True, "rejected_claims": 1}
        result["unknowns"].append("AI credibility validation failed; unsupported output was discarded.")
        if result["decision"] != "ESCALATE":
            result["decision"] = "HOLD"
        result["summary"] = f"{result['decision']}: AI credibility check failed; OVERALL_SECURITY_UNKNOWN; review deterministic evidence."
        result["escalation"]["unknowns"] = result["unknowns"]
    return result
