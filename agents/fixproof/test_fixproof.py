"""
Unit tests for the FixProof core assessment engine.

Run with:
    pytest test_fixproof.py -v
"""

import pytest

from fixproof_core import (
    assess_complaint,
    build_timeline,
    validate_complaint,
)


# ---------------------------------------------------------------------------
# Fixtures — synthetic example data
# ---------------------------------------------------------------------------

def _base_complaint(**overrides) -> dict:
    """Return a minimal valid complaint, optionally overridden."""
    base = {
        "complaint_reference": "CMP-2026-04821",
        "issue_category": "Road Maintenance",
        "location": "MG Road, Ward 12, Bengaluru",
        "original_description": (
            "Large pothole approximately 2 feet wide near bus stop causing "
            "traffic hazard."
        ),
        "original_report_date": "2026-06-15",
        "authority_status": "resolved",
        "status_update_date": "2026-07-20",
        "resolution_note": "Pothole filled with cold-mix asphalt.",
        "followup_observation": (
            "The patch has washed away after monsoon rains; the pothole is "
            "again visible and approximately the same size as originally "
            "reported."
        ),
        "followup_observation_date": "2026-09-10",
        "supporting_evidence": [
            "Photo of pothole taken on 2026-09-10 showing exposed aggregate.",
            "Measurement showing depth of approximately 6 inches.",
        ],
    }
    base.update(overrides)
    return base


# ===================================================================
# 1. Resolved complaint with a reported persistent issue
# ===================================================================

class TestResolvedWithPersistentIssue:

    def test_valid_and_discrepancy_flagged(self):
        result = assess_complaint(_base_complaint())
        assert result["valid"] is True
        assert any("DISCREPANCY" in f for f in result["analysis"]["flags"])

    def test_escalation_letter_generated(self):
        result = assess_complaint(_base_complaint())
        assert result["escalation_letter"] is not None
        assert "CMP-2026-04821" in result["escalation_letter"]
        assert "DRAFT" in result["escalation_letter"]

    def test_evidence_classified_as_unverified(self):
        result = assess_complaint(_base_complaint())
        for note in result["analysis"]["evidence_notes"]:
            assert note["classification"] == "resident_described_evidence"

    def test_followup_source_is_resident_observation(self):
        result = assess_complaint(_base_complaint())
        followup_events = [
            e for e in result["timeline"]
            if e["event"] == "Resident follow-up observation"
        ]
        assert len(followup_events) == 1
        assert followup_events[0]["source"] == "resident_observation"


# ===================================================================
# 2. Resolved complaint without a follow-up observation
# ===================================================================

class TestResolvedNoFollowup:

    def test_no_discrepancy_when_no_followup(self):
        data = _base_complaint(
            followup_observation=None,
            followup_observation_date=None,
        )
        result = assess_complaint(data)
        assert result["valid"] is True
        assert not any("DISCREPANCY" in f for f in result["analysis"]["flags"])

    def test_no_escalation_letter(self):
        data = _base_complaint(
            followup_observation=None,
            followup_observation_date=None,
        )
        result = assess_complaint(data)
        assert result["escalation_letter"] is None

    def test_missing_followup_noted(self):
        data = _base_complaint(
            followup_observation=None,
            followup_observation_date=None,
        )
        result = assess_complaint(data)
        missing = result["analysis"]["missing_info"]
        assert any("follow-up" in m.lower() for m in missing)


# ===================================================================
# 3. In-progress complaint
# ===================================================================

class TestInProgressComplaint:

    def test_no_discrepancy_for_in_progress(self):
        data = _base_complaint(authority_status="in_progress")
        result = assess_complaint(data)
        assert result["valid"] is True
        assert not any("DISCREPANCY" in f for f in result["analysis"]["flags"])

    def test_no_escalation_letter_for_in_progress(self):
        data = _base_complaint(authority_status="in_progress")
        result = assess_complaint(data)
        assert result["escalation_letter"] is None


# ===================================================================
# 4. Missing required information
# ===================================================================

class TestMissingRequiredInfo:

    @pytest.mark.parametrize("field", [
        "complaint_reference",
        "issue_category",
        "location",
        "original_description",
        "original_report_date",
        "authority_status",
    ])
    def test_each_required_field(self, field):
        data = _base_complaint(**{field: ""})
        result = assess_complaint(data)
        assert result["valid"] is False
        assert any(field in e for e in result["validation_errors"])

    def test_completely_empty_dict(self):
        result = assess_complaint({})
        assert result["valid"] is False
        assert len(result["validation_errors"]) >= len(
            [
                "complaint_reference",
                "issue_category",
                "location",
                "original_description",
                "original_report_date",
                "authority_status",
            ]
        )


# ===================================================================
# 5. Timeline ordering
# ===================================================================

class TestTimelineOrdering:

    def test_events_are_chronological(self):
        result = assess_complaint(_base_complaint())
        dates = [e["date"] for e in result["timeline"]]
        assert dates == sorted(dates)

    def test_all_three_events_present(self):
        result = assess_complaint(_base_complaint())
        assert len(result["timeline"]) == 3

    def test_reversed_dates_still_sorted(self):
        """Even when status_update is before original_report, timeline sorts."""
        data = _base_complaint(
            original_report_date="2026-09-01",
            status_update_date="2026-06-01",
            followup_observation_date="2026-10-01",
        )
        result = assess_complaint(data)
        dates = [e["date"] for e in result["timeline"]]
        assert dates == sorted(dates)


# ===================================================================
# 6. Supporting evidence & unknown statuses
# ===================================================================

class TestEvidenceAndUnknownStatus:

    def test_evidence_items_indexed(self):
        data = _base_complaint(supporting_evidence=[
            "Photo of broken drain cover.",
            "Video of water flooding street.",
            "Neighbour witness statement.",
        ])
        result = assess_complaint(data)
        indices = [n["index"] for n in result["analysis"]["evidence_notes"]]
        assert indices == [0, 1, 2]

    def test_no_evidence_flagged_as_missing(self):
        data = _base_complaint(supporting_evidence=[])
        result = assess_complaint(data)
        assert any("evidence" in m.lower() for m in result["analysis"]["missing_info"])

    def test_unknown_status_flagged(self):
        data = _base_complaint(authority_status="forwarded_to_zonal_office")
        result = assess_complaint(data)
        assert result["valid"] is True
        assert any("Unrecognised" in f for f in result["analysis"]["flags"])
        assert result["analysis"]["status_recognised"] is False

    def test_known_status_recognised(self):
        data = _base_complaint(authority_status="pending")
        result = assess_complaint(data)
        assert result["analysis"]["status_recognised"] is True


# ===================================================================
# 7. Invalid input
# ===================================================================

class TestInvalidInput:

    def test_non_dict_input(self):
        result = assess_complaint("not a dict")
        assert result["valid"] is False
        assert "dictionary" in result["validation_errors"][0].lower()

    def test_none_input(self):
        result = assess_complaint(None)
        assert result["valid"] is False

    def test_list_input(self):
        result = assess_complaint([1, 2, 3])
        assert result["valid"] is False

    def test_invalid_date_format(self):
        data = _base_complaint(original_report_date="15-06-2026")
        result = assess_complaint(data)
        assert result["valid"] is False
        assert any("date" in e.lower() for e in result["validation_errors"])

    def test_evidence_wrong_type(self):
        data = _base_complaint(supporting_evidence="just a string")
        result = assess_complaint(data)
        assert result["valid"] is False
        assert any("list" in e.lower() for e in result["validation_errors"])

    def test_metadata_always_present(self):
        """Even invalid input should include metadata with disclaimer."""
        result = assess_complaint(None)
        assert "metadata" in result
        assert "disclaimer" in result["metadata"]

    def test_result_structure_on_invalid(self):
        """All top-level keys should be present even for invalid input."""
        result = assess_complaint(42)
        expected_keys = {
            "valid",
            "validation_errors",
            "timeline",
            "analysis",
            "escalation_letter",
            "metadata",
        }
        assert expected_keys.issubset(result.keys())

    def test_whitespace_only_required_field(self):
        """A field containing only spaces should be treated as missing."""
        data = _base_complaint(complaint_reference="   ")
        result = assess_complaint(data)
        assert result["valid"] is False
        assert any("complaint_reference" in e for e in result["validation_errors"])

    def test_invalid_optional_date(self):
        """A malformed status_update_date should fail validation."""
        data = _base_complaint(status_update_date="July 20 2026")
        result = assess_complaint(data)
        assert result["valid"] is False
        assert any("status_update_date" in e for e in result["validation_errors"])


# ===================================================================
# 8. Additional edge cases found during code review
# ===================================================================

class TestClosedStatusDiscrepancy:
    """'closed' should behave like 'resolved' for discrepancy detection."""

    def test_closed_with_followup_triggers_discrepancy(self):
        data = _base_complaint(authority_status="closed")
        result = assess_complaint(data)
        assert any("DISCREPANCY" in f for f in result["analysis"]["flags"])

    def test_closed_with_followup_generates_letter(self):
        data = _base_complaint(authority_status="closed")
        result = assess_complaint(data)
        assert result["escalation_letter"] is not None


class TestTimelinePartialDates:
    """Timeline should work correctly when optional dates are absent."""

    def test_only_report_date_present(self):
        data = _base_complaint(
            status_update_date=None,
            followup_observation_date=None,
            followup_observation=None,
        )
        result = assess_complaint(data)
        assert len(result["timeline"]) == 1
        assert result["timeline"][0]["event"] == "Complaint filed"

    def test_two_dates_no_followup(self):
        data = _base_complaint(
            followup_observation_date=None,
            followup_observation=None,
        )
        result = assess_complaint(data)
        assert len(result["timeline"]) == 2


class TestEscalationLetterContent:
    """Verify the letter uses only supplied data and never invents facts."""

    def test_letter_contains_only_supplied_reference(self):
        result = assess_complaint(_base_complaint())
        letter = result["escalation_letter"]
        assert "CMP-2026-04821" in letter
        # Should NOT contain placeholder brackets for fields that were supplied
        assert "[Reference]" not in letter

    def test_letter_uses_placeholder_when_no_status_date(self):
        """When status_update_date is absent, the letter must not invent one."""
        data = _base_complaint(status_update_date=None)
        result = assess_complaint(data)
        letter = result["escalation_letter"]
        assert letter is not None
        # Should say status-update date is not available, not invent a date
        assert "no status-update date" in letter.lower() or "not available" in letter.lower()

    def test_letter_includes_review_disclaimer(self):
        result = assess_complaint(_base_complaint())
        letter = result["escalation_letter"]
        assert "review and edit" in letter.lower()

    def test_letter_labels_evidence_as_resident_provided(self):
        result = assess_complaint(_base_complaint())
        letter = result["escalation_letter"]
        assert "provided by the resident" in letter.lower()


class TestInputImmutability:
    """assess_complaint must not mutate the caller's dictionary."""

    def test_input_dict_unchanged_after_assessment(self):
        import copy
        data = _base_complaint()
        original = copy.deepcopy(data)
        assess_complaint(data)
        assert data == original


class TestSourceProvenanceHonesty:
    """Regression tests preventing misleading source-provenance claims."""

    def test_no_reported_fact_label_used(self):
        result = assess_complaint(_base_complaint())
        sources = [e["source"] for e in result["timeline"]]
        assert "reported_fact" not in sources
        assert "reported_fact" not in result["metadata"]["source_classifications"]

    def test_no_source_claims_unverified_fact(self):
        """No source label should claim to be a 'fact' or 'verified'."""
        result = assess_complaint(_base_complaint())
        for event in result["timeline"]:
            assert "fact" not in event["source"].lower()
            assert "verified" not in event["source"].lower()
        for note in result["analysis"]["evidence_notes"]:
            assert "fact" not in note["classification"].lower()

    def test_sources_distinguish_complaint_status_and_observation(self):
        """Timeline events must distinguish complaint, status, and observation sources."""
        result = assess_complaint(_base_complaint())
        timeline_by_event = {e["event"]: e["source"] for e in result["timeline"]}
        assert timeline_by_event["Complaint filed"] == "user_supplied_complaint"
        assert timeline_by_event["Authority status update"] == "user_supplied_status"
        assert timeline_by_event["Resident follow-up observation"] == "resident_observation"

    def test_evidence_classification_label(self):
        result = assess_complaint(_base_complaint())
        for note in result["analysis"]["evidence_notes"]:
            assert note["classification"] == "resident_described_evidence"

    def test_metadata_explicitly_disclaims_independent_verification(self):
        """Legend descriptions must disclaim independent verification."""
        result = assess_complaint(_base_complaint())
        legend = result["metadata"]["source_classifications"]
        for key, description in legend.items():
            assert "not independently verified" in description.lower()


# ===================================================================
# 10. Agent and tool integration tests (no live API key needed)
# ===================================================================

class TestAgentToolIntegration:
    """Verifies that the ADK tool wrapper and root_agent are configured correctly."""

    def test_tool_full_complaint_invocation(self):
        from agent import analyse_civic_complaint
        res = analyse_civic_complaint(
            complaint_reference="CMP-TEST-999",
            issue_category="Roads",
            location="MG Road",
            original_description="Broken asphalt",
            original_report_date="2026-01-01",
            authority_status="resolved",
            status_update_date="2026-01-10",
            resolution_note="Cold mix applied",
            followup_observation="Crater has reappeared",
            followup_observation_date="2026-01-20",
            supporting_evidence=["Photo of crater"],
        )
        assert res["valid"] is True
        assert any("DISCREPANCY" in f for f in res["analysis"]["flags"])
        assert len(res["timeline"]) == 3
        assert res["escalation_letter"] is not None
        assert "CMP-TEST-999" in res["escalation_letter"]
        assert res["analysis"]["evidence_notes"][0]["classification"] == "resident_described_evidence"

    def test_tool_required_fields_only(self):
        from agent import analyse_civic_complaint
        res = analyse_civic_complaint(
            complaint_reference="CMP-REQ-ONLY",
            issue_category="Sanitation",
            location="Sector 4",
            original_description="Overflowing bin",
            original_report_date="2026-02-01",
            authority_status="in_progress",
        )
        assert res["valid"] is True
        assert len(res["timeline"]) == 1
        assert res["timeline"][0]["event"] == "Complaint filed"
        assert res["escalation_letter"] is None
        missing = res["analysis"]["missing_info"]
        assert any("status-update date" in m.lower() for m in missing)
        assert any("resolution note" in m.lower() for m in missing)
        assert any("follow-up observation" in m.lower() for m in missing)

    def test_tool_normalizes_string_evidence(self):
        from agent import analyse_civic_complaint
        res = analyse_civic_complaint(
            complaint_reference="CMP-NORM-1",
            issue_category="Water",
            location="Main valve",
            original_description="Leak",
            original_report_date="2026-03-01",
            authority_status="open",
            supporting_evidence="Single photo string",
        )
        assert res["valid"] is True
        assert len(res["analysis"]["evidence_notes"]) == 1
        assert res["analysis"]["evidence_notes"][0]["description"] == "Single photo string"

    def test_tool_missing_required_returns_invalid(self):
        from agent import analyse_civic_complaint
        res = analyse_civic_complaint(
            complaint_reference="",
            issue_category="Roads",
            location="Corner",
            original_description="Pothole",
            original_report_date="2026-01-01",
            authority_status="resolved",
        )
        assert res["valid"] is False
        assert any("complaint_reference" in e for e in res["validation_errors"])

    def test_root_agent_configuration(self):
        import os
        from agent import root_agent, analyse_civic_complaint, DEFAULT_MODEL
        assert root_agent.name == "fixproof"
        assert analyse_civic_complaint in root_agent.tools
        expected_model = os.environ.get("FIXPROOF_MODEL", DEFAULT_MODEL)
        assert root_agent.model == expected_model

    def test_agent_instruction_contains_required_directives(self):
        from agent import root_agent
        instruction = str(root_agent.instruction)
        # Direct tool invocation directive
        assert "DIRECT TOOL INVOCATION" in instruction
        assert "DO NOT ask the user to confirm, repeat, or provide fields they have already supplied" in instruction
        # Incomplete input handling
        assert "ONLY if one or more of the 6 REQUIRED fields are genuinely absent" in instruction
        # Consolidated single response
        assert "CONSOLIDATED SINGLE-RESPONSE OUTPUT" in instruction
        assert "ONE concise, consolidated response" in instruction
        # Required structured sections
        assert "Assessment Summary" in instruction
        assert "Chronological Timeline" in instruction
        assert "Discrepancy Flags" in instruction
        assert "Missing Information" in instruction
        assert "Source & Evidence Classifications" in instruction
        assert "Escalation Letter" in instruction
        # Epistemic honesty
        assert "EPISTEMIC HONESTY" in instruction
        assert "Never invent dates" in instruction


# ===================================================================
# 11. Streamlit UI data preparation & integration tests
# ===================================================================

class TestUIIntegration:
    """Verifies that app.py data parsing and integration operate deterministically."""

    def test_app_module_imports_cleanly(self):
        import app
        assert hasattr(app, "prepare_complaint_dict")
        assert hasattr(app, "DEMO_DATA")

    def test_prepare_complaint_dict_full(self):
        from app import prepare_complaint_dict
        d = prepare_complaint_dict(
            complaint_reference="  CMP-UI-01  ",
            issue_category=" Roads ",
            location=" Main Rd ",
            original_description=" Deep pothole ",
            original_report_date=" 2026-05-01 ",
            authority_status=" resolved ",
            status_update_date=" 2026-05-10 ",
            resolution_note=" Fixed with patch ",
            followup_observation=" Patch washed away ",
            followup_observation_date=" 2026-05-20 ",
            evidence_text=" Photo 1 \n\n Photo 2 with depth ruler \n ",
        )
        assert d["complaint_reference"] == "CMP-UI-01"
        assert d["issue_category"] == "Roads"
        assert d["location"] == "Main Rd"
        assert d["original_description"] == "Deep pothole"
        assert d["original_report_date"] == "2026-05-01"
        assert d["authority_status"] == "resolved"
        assert d["status_update_date"] == "2026-05-10"
        assert d["resolution_note"] == "Fixed with patch"
        assert d["followup_observation"] == "Patch washed away"
        assert d["followup_observation_date"] == "2026-05-20"
        assert d["supporting_evidence"] == ["Photo 1", "Photo 2 with depth ruler"]

    def test_prepare_complaint_dict_minimal(self):
        from app import prepare_complaint_dict
        d = prepare_complaint_dict(
            complaint_reference="CMP-MIN",
            issue_category="Water",
            location="Block A",
            original_description="Broken pipe",
            original_report_date="2026-06-01",
            authority_status="open",
            status_update_date="",
            resolution_note="",
            followup_observation="",
            followup_observation_date="",
            evidence_text="",
        )
        assert "status_update_date" not in d
        assert "resolution_note" not in d
        assert "followup_observation" not in d
        assert "supporting_evidence" not in d
        res = assess_complaint(d)
        assert res["valid"] is True

    def test_demo_data_is_valid_and_flags_discrepancy(self):
        from app import DEMO_DATA, prepare_complaint_dict
        complaint = prepare_complaint_dict(**DEMO_DATA)
        res = assess_complaint(complaint)
        assert res["valid"] is True
        assert any("DISCREPANCY" in f for f in res["analysis"]["flags"])
        assert res["escalation_letter"] is not None
        assert len(res["timeline"]) == 3
        assert len(res["analysis"]["evidence_notes"]) == 2
