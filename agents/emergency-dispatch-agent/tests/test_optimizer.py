
from emergency_dispatch.guardrails.input_validation import parse_scenario
from emergency_dispatch.optimizer import optimize_dispatch


def test_selects_fastest_eligible_ambulance():
    scenario = {
        "incident": {
            "id": "EMG-1",
            "severity": "critical",
            "location": "Central Market",
            "required_capabilities": ["advanced-life-support"],
        },
        "ambulances": [
            {
                "id": "AMB-01",
                "location": "Station A",
                "available": True,
                "capabilities": ["advanced-life-support"],
                "estimated_travel_minutes": 5,
            },
            {
                "id": "AMB-02",
                "location": "Station B",
                "available": True,
                "capabilities": ["advanced-life-support"],
                "estimated_travel_minutes": 8,
            },
            {
                "id": "AMB-03",
                "location": "Station C",
                "available": False,
                "capabilities": ["advanced-life-support"],
                "estimated_travel_minutes": 2,
            },
        ],
        "hospitals": [],
    }

    incident, ambulances, _ = parse_scenario(scenario)
    result = optimize_dispatch(incident, ambulances)

    assert result.status == "recommendation_available"
    assert result.selected_ambulance.ambulance_id == "AMB-01"
    assert [a.ambulance_id for a in result.alternatives] == ["AMB-02"]
    assert result.human_approval_required is True
    assert any(e.resource_id == "AMB-03" for e in result.exclusions)


def test_returns_no_eligible_ambulance_when_capabilities_are_missing():
    scenario = {
        "incident": {
            "id": "EMG-2",
            "severity": "critical",
            "location": "Central Market",
            "required_capabilities": ["advanced-life-support"],
        },
        "ambulances": [
            {
                "id": "AMB-01",
                "location": "Station A",
                "available": True,
                "capabilities": ["basic-life-support"],
                "estimated_travel_minutes": 3,
            }
        ],
        "hospitals": [],
    }

    incident, ambulances, _ = parse_scenario(scenario)
    result = optimize_dispatch(incident, ambulances)

    assert result.status == "no_eligible_ambulance"
    assert result.selected_ambulance is None
    assert result.exclusions[0].resource_id == "AMB-01"
