from emergency_dispatch.guardrails.input_validation import parse_scenario
from emergency_dispatch.hospital_matcher import match_hospitals


def test_ranks_hospitals_that_cover_required_capabilities():
    scenario = {
        "incident": {
            "id": "EMG-3",
            "severity": "critical",
            "location": "Central Market",
            "required_capabilities": ["advanced-life-support"],
            "required_hospital_capabilities": ["emergency", "critical-care"],
        },
        "ambulances": [],
        "hospitals": [
            {
                "id": "HOSP-01",
                "name": "Central General",
                "available_capabilities": ["emergency", "critical-care"],
                "estimated_travel_minutes": 6,
                "capacity_available": True,
            },
            {
                "id": "HOSP-02",
                "name": "North Medical Center",
                "available_capabilities": ["emergency"],
                "estimated_travel_minutes": 2,
                "capacity_available": True,
            },
            {
                "id": "HOSP-03",
                "name": "West Hospital",
                "available_capabilities": ["emergency", "critical-care"],
                "estimated_travel_minutes": 4,
                "capacity_available": False,
            },
        ],
    }

    incident, _, hospitals = parse_scenario(scenario)
    result = match_hospitals(incident, hospitals)

    assert [hospital.hospital_id for hospital in result] == ["HOSP-01"]


def test_returns_empty_when_no_hospital_is_eligible():
    scenario = {
        "incident": {
            "id": "EMG-4",
            "severity": "critical",
            "location": "Central Market",
            "required_capabilities": ["advanced-life-support"],
            "required_hospital_capabilities": ["critical-care"],
        },
        "ambulances": [],
        "hospitals": [
            {
                "id": "HOSP-01",
                "name": "Small Clinic",
                "available_capabilities": ["emergency"],
                "estimated_travel_minutes": 3,
                "capacity_available": True,
            }
        ],
    }

    incident, _, hospitals = parse_scenario(scenario)

    assert match_hospitals(incident, hospitals) == []
