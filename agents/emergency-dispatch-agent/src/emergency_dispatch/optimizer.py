
from emergency_dispatch.models import (
    Ambulance,
    AmbulanceCandidate,
    DispatchRecommendation,
    Exclusion,
    Incident,
)


def optimize_dispatch(
    incident: Incident,
    ambulances: list[Ambulance],
) -> DispatchRecommendation:
    """Rank eligible ambulances using capabilities and estimated travel time.

    This is deterministic decision support, not a real-world dispatch system.
    A human dispatcher must review every recommendation.
    """
    candidates: list[AmbulanceCandidate] = []
    exclusions: list[Exclusion] = []

    for ambulance in ambulances:
        reasons: list[str] = []

        if not ambulance.available:
            reasons.append("Ambulance is unavailable.")

        missing_capabilities = (
            incident.required_capabilities - ambulance.capabilities
        )
        if missing_capabilities:
            reasons.append(
                "Missing required capabilities: "
                + ", ".join(sorted(missing_capabilities))
                + "."
            )

        if reasons:
            exclusions.append(
                Exclusion(
                    resource_id=ambulance.ambulance_id,
                    reasons=tuple(reasons),
                )
            )
            continue

        candidates.append(
            AmbulanceCandidate(
                ambulance_id=ambulance.ambulance_id,
                estimated_travel_minutes=ambulance.estimated_travel_minutes,
                matched_capabilities=(
                    incident.required_capabilities & ambulance.capabilities
                ),
            )
        )

    # Stable tie-breaking makes recommendations reproducible.
    candidates.sort(
        key=lambda candidate: (
            candidate.estimated_travel_minutes,
            candidate.ambulance_id,
        )
    )

    if not candidates:
        return DispatchRecommendation(
            status="no_eligible_ambulance",
            incident_id=incident.incident_id,
            selected_ambulance=None,
            exclusions=tuple(exclusions),
            explanation=(
                "No ambulance met all availability and capability "
                "requirements. Human review is required."
            ),
            human_approval_required=True,
            warnings=(
                "Travel times are supplied estimates, not live traffic data.",
            ),
        )

    selected = candidates[0]
    alternatives = tuple(candidates[1:])

    return DispatchRecommendation(
        status="recommendation_available",
        incident_id=incident.incident_id,
        selected_ambulance=selected,
        alternatives=alternatives,
        exclusions=tuple(exclusions),
        explanation=(
            f"{selected.ambulance_id} is the highest-ranked eligible option "
            f"with a supplied estimated travel time of "
            f"{selected.estimated_travel_minutes:g} minutes. "
            "The ranking considers eligibility and estimated travel time only."
        ),
        human_approval_required=True,
        warnings=(
            "Travel times are supplied estimates, not live traffic data.",
            "This recommendation requires review by a human dispatcher.",
        ),
    )
