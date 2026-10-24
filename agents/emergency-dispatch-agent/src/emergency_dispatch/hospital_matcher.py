from emergency_dispatch.models import Hospital, Incident


def match_hospitals(
    incident: Incident,
    hospitals: list[Hospital],
) -> list[Hospital]:
    """Filter hospitals by required capabilities and available capacity."""
    required = incident.required_hospital_capabilities

    eligible = [
        hospital
        for hospital in hospitals
        if hospital.capacity_available
        and required.issubset(hospital.available_capabilities)
    ]

    return sorted(
        eligible,
        key=lambda hospital: (
            hospital.estimated_travel_minutes,
            hospital.hospital_id,
        ),
    )
