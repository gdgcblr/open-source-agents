
import math
from typing import Any

from emergency_dispatch.models import Ambulance, Hospital, Incident


VALID_SEVERITIES = {"low", "moderate", "high", "critical"}


class InputValidationError(ValueError):
    """Raised when scenario data fails validation."""


def _require_object(value: Any, field_name: str) -> dict:
    if not isinstance(value, dict):
        raise InputValidationError(f"'{field_name}' must be an object.")
    return value


def _require_non_empty_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InputValidationError(
            f"'{field_name}' must be a non-empty string."
        )
    return value.strip()


def _require_string_list(value: Any, field_name: str) -> frozenset[str]:
    if not isinstance(value, list):
        raise InputValidationError(f"'{field_name}' must be a list.")

    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise InputValidationError(
            f"Every item in '{field_name}' must be a non-empty string."
        )

    return frozenset(item.strip() for item in value)


def _require_boolean(value: Any, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise InputValidationError(f"'{field_name}' must be a boolean.")
    return value


def _require_travel_time(value: Any, field_name: str) -> float:
    # bool is a subclass of int in Python, so reject it explicitly.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InputValidationError(f"'{field_name}' must be a number.")

    if not math.isfinite(value) or value < 0:
        raise InputValidationError(
            f"'{field_name}' must be finite and non-negative."
        )

    return float(value)


def parse_scenario(
    data: dict[str, Any],
) -> tuple[Incident, list[Ambulance], list[Hospital]]:
    """Validate scenario data and convert it into domain models."""
    root = _require_object(data, "scenario")
    raw_incident = _require_object(root.get("incident"), "incident")

    incident_id = _require_non_empty_string(
        raw_incident.get("id"), "incident.id"
    )

    severity = raw_incident.get("severity")
    if not isinstance(severity, str) or severity not in VALID_SEVERITIES:
        raise InputValidationError(
            f"'incident.severity' must be one of "
            f"{sorted(VALID_SEVERITIES)}."
        )

    location = _require_non_empty_string(
        raw_incident.get("location"), "incident.location"
    )

    required_capabilities = _require_string_list(
        raw_incident.get("required_capabilities", []),
        "incident.required_capabilities",
    )

    required_hospital_capabilities = _require_string_list(
        raw_incident.get("required_hospital_capabilities", []),
        "incident.required_hospital_capabilities",
    )

    raw_ambulances = root.get("ambulances")
    if not isinstance(raw_ambulances, list):
        raise InputValidationError("'ambulances' must be a list.")

    ambulances: list[Ambulance] = []
    ambulance_ids: set[str] = set()

    for index, item in enumerate(raw_ambulances):
        field = f"ambulances[{index}]"
        raw = _require_object(item, field)

        ambulance_id = _require_non_empty_string(
            raw.get("id"), f"{field}.id"
        )
        if ambulance_id in ambulance_ids:
            raise InputValidationError(
                f"Duplicate ambulance ID: '{ambulance_id}'."
            )
        ambulance_ids.add(ambulance_id)

        ambulances.append(
            Ambulance(
                ambulance_id=ambulance_id,
                location=_require_non_empty_string(
                    raw.get("location"), f"{field}.location"
                ),
                available=_require_boolean(
                    raw.get("available"), f"{field}.available"
                ),
                capabilities=_require_string_list(
                    raw.get("capabilities"), f"{field}.capabilities"
                ),
                estimated_travel_minutes=_require_travel_time(
                    raw.get("estimated_travel_minutes"),
                    f"{field}.estimated_travel_minutes",
                ),
            )
        )

    raw_hospitals = root.get("hospitals")
    if not isinstance(raw_hospitals, list):
        raise InputValidationError("'hospitals' must be a list.")

    hospitals: list[Hospital] = []
    hospital_ids: set[str] = set()

    for index, item in enumerate(raw_hospitals):
        field = f"hospitals[{index}]"
        raw = _require_object(item, field)

        hospital_id = _require_non_empty_string(
            raw.get("id"), f"{field}.id"
        )
        if hospital_id in hospital_ids:
            raise InputValidationError(
                f"Duplicate hospital ID: '{hospital_id}'."
            )
        hospital_ids.add(hospital_id)

        hospitals.append(
            Hospital(
                hospital_id=hospital_id,
                name=_require_non_empty_string(
                    raw.get("name"), f"{field}.name"
                ),
                available_capabilities=_require_string_list(
                    raw.get("available_capabilities"),
                    f"{field}.available_capabilities",
                ),
                estimated_travel_minutes=_require_travel_time(
                    raw.get("estimated_travel_minutes"),
                    f"{field}.estimated_travel_minutes",
                ),
                capacity_available=_require_boolean(
                    raw.get("capacity_available", True),
                    f"{field}.capacity_available",
                ),
            )
        )

    incident = Incident(
        incident_id=incident_id,
        severity=severity,
        location=location,
        required_capabilities=required_capabilities,
        required_hospital_capabilities=required_hospital_capabilities,
    )

    return incident, ambulances, hospitals
