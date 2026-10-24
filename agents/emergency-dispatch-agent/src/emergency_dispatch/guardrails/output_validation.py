
from emergency_dispatch.models import DispatchRecommendation


def validate_recommendation(
    recommendation: DispatchRecommendation,
) -> list[str]:
    """Return validation errors for an invalid recommendation."""
    errors: list[str] = []

    if recommendation.human_approval_required is not True:
        errors.append("Human approval must remain required.")

    if recommendation.status == "recommendation_available":
        if recommendation.selected_ambulance is None:
            errors.append(
                "A successful recommendation must include a selected ambulance."
            )

    elif recommendation.selected_ambulance is not None:
        errors.append(
            "A recommendation must not select an ambulance for this status."
        )

    if recommendation.selected_ambulance is not None:
        if recommendation.selected_ambulance.estimated_travel_minutes < 0:
            errors.append("Selected ambulance travel time cannot be negative.")

    for candidate in recommendation.alternatives:
        if candidate.estimated_travel_minutes < 0:
            errors.append("Alternative ambulance travel time cannot be negative.")

    return errors
