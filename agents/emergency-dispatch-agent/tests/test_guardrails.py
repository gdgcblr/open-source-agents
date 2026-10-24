
import pytest

from emergency_dispatch.guardrails.input_validation import (
    InputValidationError,
    parse_scenario,
)


def valid_scenario():
    return {
        "incident": {
            "id": "EMG-1001",
            "severity": "critical",
            "location": "Central Market",
            "required_capabilities": ["advanced-life-support"],
        },
        "ambulances": [
            {
                "id": "AMB-01",
                "location": "Central Station",
                "available": True,
                "capabilities": ["advanced-life-support"],
                "estimated_travel_minutes": 5,
            }
        ],
        "hospitals": [
            {
                "id": "HOSP-01",
                "name": "Central General",
                "available_capabilities": ["emergency", "critical-care"],
                "estimated_travel_minutes": 6,
                "capacity_available": True,
            }
        ],
    }


def test_parses_valid_scenario():
    incident, ambulances, hospitals = parse_scenario(valid_scenario())

    assert incident.incident_id == "EMG-1001"
    assert incident.severity == "critical"
    assert ambulances[0].ambulance_id == "AMB-01"
    assert hospitals[0].hospital_id == "HOSP-01"


def test_rejects_negative_travel_time():
    scenario = valid_scenario()
    scenario["ambulances"][0]["estimated_travel_minutes"] = -2

    with pytest.raises(InputValidationError):
        parse_scenario(scenario)


def test_rejects_duplicate_ambulance_ids():
    scenario = valid_scenario()
    scenario["ambulances"].append(
        {**scenario["ambulances"][0], "location": "Another location"}
    )

    with pytest.raises(InputValidationError, match="Duplicate ambulance ID"):
        parse_scenario(scenario)


def test_rejects_invalid_severity():
    scenario = valid_scenario()
    scenario["incident"]["severity"] = "extreme"

    with pytest.raises(InputValidationError, match="incident.severity"):
        parse_scenario(scenario)
