"""Offline tests for the agent's tools and data. No API key needed."""

from namma_civic_agent import tools
from namma_civic_agent.prompt import INSTRUCTION

SEVERITIES = {"low", "medium", "high", "critical"}


def test_list_issue_types_returns_all_categories():
    result = tools.list_issue_types()
    ids = [t["id"] for t in result["issue_types"]]
    assert result["status"] == "success"
    assert "pothole" in ids and "other" in ids
    assert len(ids) == len(set(ids)), "issue type ids must be unique"


def test_every_issue_type_maps_to_a_known_authority():
    for issue in tools._issue_types():
        assert issue["default_severity"] in SEVERITIES, issue["id"]
        assert tools._get_authority(issue["authority_id"]) is not None, issue["id"]


def test_find_department_routes_streetlight_to_city_not_bescom():
    result = tools.find_department("streetlight")
    assert result["status"] == "success"
    assert result["authority_id"] == "city_corporation"
    assert result["department"] == "Electrical"


def test_find_department_accepts_loose_input():
    assert tools.find_department("  Pothole ")["issue_type"] == "pothole"
    assert tools.find_department("Electrical Hazard")["issue_type"] == "electrical_hazard"


def test_find_department_unknown_type_lists_valid_ids():
    result = tools.find_department("alien landing")
    assert result["status"] == "error"
    assert "garbage" in result["valid_issue_types"]


def test_filing_channels_flag_unverified_and_skip_missing_values():
    result = tools.get_filing_channels("bwssb")
    assert result["status"] == "success"
    assert all(c["value"] for c in result["channels"])
    for channel in result["channels"]:
        if not channel["verified"]:
            assert "warning" in channel
    assert result["emergency"]["value"] == "112"
    assert result["escalation_path"]


def test_filing_channels_unknown_authority():
    result = tools.get_filing_channels("ministry_of_magic")
    assert result["status"] == "error"
    assert "bescom" in result["valid_authority_ids"]


def test_save_complaint_writes_markdown(tmp_path, monkeypatch):
    monkeypatch.setenv("COMPLAINTS_DIR", str(tmp_path))
    result = tools.save_complaint(
        issue_type="pothole",
        location="100 Feet Road, Indiranagar",
        severity="high",
        complaint_english="Subject: Pothole on 100 Feet Road",
        complaint_kannada="ವಿಷಯ: ರಸ್ತೆ ಗುಂಡಿ",
    )
    assert result["status"] == "success"
    text = (tmp_path / result["saved_to"].split("/")[-1]).read_text(encoding="utf-8")
    assert "Indiranagar" in text and "ರಸ್ತೆ ಗುಂಡಿ" in text


def test_instruction_has_no_state_placeholders():
    # ADK would try to substitute session state for anything in curly braces.
    assert "{" not in INSTRUCTION and "}" not in INSTRUCTION
