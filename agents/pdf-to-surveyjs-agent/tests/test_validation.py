from __future__ import annotations

import json

from pdf_to_surveyjs_agent.tools import (
    normalize_survey,
    validate_survey,
    validate_survey_json,
)


def test_accepts_top_level_elements() -> None:
    survey = {
        "title": "Registration",
        "elements": [
            {"type": "text", "name": "full_name", "title": "Full name", "isRequired": True},
            {
                "type": "radiogroup",
                "name": "attendance",
                "title": "Will you attend?",
                "choices": ["Yes", "No"],
            },
        ],
    }

    result = validate_survey(survey)

    assert result.valid is True
    assert result.errors == []


def test_accepts_pages_and_choice_objects() -> None:
    survey = {
        "pages": [
            {
                "name": "page1",
                "elements": [
                    {
                        "type": "dropdown",
                        "name": "department",
                        "title": "Department",
                        "choices": [
                            {"value": "eng", "text": "Engineering"},
                            {"value": "ops", "text": "Operations"},
                        ],
                    }
                ],
            }
        ]
    }

    assert validate_survey(survey).valid is True


def test_rejects_invalid_json() -> None:
    result = validate_survey_json('{"elements": [}')

    assert result["valid"] is False
    assert "Invalid JSON" in result["errors"][0]


def test_rejects_missing_structure() -> None:
    result = validate_survey({"title": "Empty"})

    assert result.valid is False
    assert "elements" in result.errors[0]


def test_rejects_unsupported_type_and_duplicate_names() -> None:
    survey = {
        "elements": [
            {"type": "text", "name": "email", "title": "Email"},
            {"type": "text", "name": "email", "title": "Confirm email"},
            {"type": "madeup", "name": "other", "title": "Other"},
        ]
    }

    result = validate_survey(survey)

    assert result.valid is False
    assert any("Duplicate" in error for error in result.errors)
    assert any("not supported" in error for error in result.errors)


def test_choice_question_requires_choices() -> None:
    result = validate_survey(
        {"elements": [{"type": "radiogroup", "name": "answer", "title": "Answer"}]}
    )

    assert result.valid is False
    assert any("choices" in error for error in result.errors)


def test_required_and_visibility_types_are_checked() -> None:
    result = validate_survey(
        {
            "elements": [
                {
                    "type": "text",
                    "name": "details",
                    "title": "Details",
                    "isRequired": "yes",
                    "visibleIf": True,
                }
            ]
        }
    )

    assert result.valid is False
    assert len(result.errors) == 2


def test_json_validator_accepts_serialized_survey() -> None:
    payload = json.dumps(
        {"elements": [{"type": "boolean", "name": "consent", "title": "I agree"}]}
    )

    result = validate_survey_json(payload)

    assert result == {"valid": True, "errors": [], "warnings": []}


def test_rejects_mixed_page_and_top_level_layout() -> None:
    result = validate_survey(
        {
            "pages": [{"name": "about", "elements": []}],
            "elements": [{"type": "text", "name": "surname", "title": "Surname"}],
        }
    )

    assert result.valid is False
    assert any("cannot mix" in error for error in result.errors)


def test_missing_question_title_is_an_error() -> None:
    result = validate_survey({"elements": [{"type": "text", "name": "surname"}]})

    assert result.valid is False
    assert any("title must be" in error for error in result.errors)


def test_normalizes_unmapped_root_questions_into_an_additional_page() -> None:
    survey, warnings = normalize_survey(
        {
            "pages": [{"name": "about", "elements": []}],
            "elements": [{"type": "text", "name": "notes"}],
        }
    )

    assert "elements" not in survey
    assert survey["pages"] == [
        {
            "name": "additional_questions",
            "title": "Additional questions",
            "elements": [
                {"type": "text", "name": "notes", "title": "Notes"}
            ],
        }
    ]
    assert warnings == [
        "Placed 1 question(s) without a page reference in Additional questions.",
        "Removed 1 empty page(s).",
    ]


def test_normalizes_model_page_layout_titles_and_conditions() -> None:
    survey, warnings = normalize_survey(
        {
            "pages": [
                {"name": "Tell us about you"},
                {"name": "Family details", "elements": []},
                {"name": "Unused section", "elements": []},
            ],
            "elements": [
                {"page": 1, "type": "text", "name": "first_middle_names"},
                {
                    "page": 1,
                    "type": "text",
                    "name": "gender_other_text",
                    "visibleIf": '"{gender}" = "Other"',
                },
                {
                    "page": 2,
                    "type": "text",
                    "name": "ethnicity_other_text",
                    "visibleIf": '"{ethnicity} contains \'Other\'"',
                },
            ],
        }
    )

    assert "elements" not in survey
    assert len(survey["pages"]) == 2
    assert survey["pages"][0]["name"] == "tell_us_about_you"
    assert survey["pages"][0]["title"] == "Tell us about you"
    assert survey["pages"][0]["elements"][0] == {
        "type": "text",
        "name": "first_middle_names",
        "title": "First middle names",
    }
    assert survey["pages"][0]["elements"][1]["visibleIf"] == "{gender} = 'Other'"
    assert survey["pages"][1]["elements"][0]["visibleIf"] == (
        "{ethnicity} contains 'Other'"
    )
    assert validate_survey(survey).valid is True
    assert warnings == [
        "Moved 3 question(s) from top-level elements into their pages.",
        "Removed 1 empty page(s).",
    ]


def test_normalize_survey_recovers_missing_types_and_choice_aliases() -> None:
    raw = {
        "pages": [
            {
                "name": "details",
                "elements": [
                    {
                        "type": "radiogroup",
                        "name": "work_with_lawyer",
                        "title": "Are you working with a lawyer?",
                        "options": ["Yes", "No"],
                    },
                    {
                        "name": "lawyer_name",
                        "title": "Lawyer name",
                    },
                    {
                        "type": "checkbox",
                        "name": "contact_method",
                        "title": "Preferred contact",
                        "items": ["Email", "Phone"],
                    },
                ],
            }
        ]
    }

    survey, _ = normalize_survey(raw)
    result = validate_survey(survey)

    assert result.valid is True
    assert survey["pages"][0]["elements"][0]["choices"] == ["Yes", "No"]
    assert survey["pages"][0]["elements"][1]["type"] == "text"
    assert survey["pages"][0]["elements"][2]["choices"] == ["Email", "Phone"]


def test_normalize_survey_recovers_string_elements_and_html_elements() -> None:
    raw = {
        "pages": [
            {
                "name": "personal",
                "elements": [
                    "Full name (required)",
                    "Date of birth",
                    "Email address",
                    "Tell us your story in detail",
                    "Do you have a passport?",
                ],
            },
            {
                "name": "declarations",
                "elements": [
                    {
                        "type": "html",
                        "title": "Please read these terms carefully before submitting.",
                    },
                    {
                        "type": "text",
                        "name": "full_name",  # Duplicate name from page 1!
                        "title": "Confirm Full Name",
                    },
                ],
            },
        ]
    }

    survey, _ = normalize_survey(raw)
    result = validate_survey(survey)

    assert result.valid is True
    assert len(survey["pages"][0]["elements"]) == 5
    assert survey["pages"][0]["elements"][0]["name"] == "full_name"
    assert survey["pages"][0]["elements"][0]["isRequired"] is True
    assert survey["pages"][0]["elements"][1]["inputType"] == "date"
    assert survey["pages"][0]["elements"][2]["inputType"] == "email"
    assert survey["pages"][0]["elements"][3]["type"] == "comment"
    assert survey["pages"][0]["elements"][4]["type"] == "radiogroup"
    assert survey["pages"][0]["elements"][4]["choices"] == ["Yes", "No"]

    # HTML question fixed
    assert survey["pages"][1]["elements"][0]["type"] == "html"
    assert survey["pages"][1]["elements"][0]["html"] == "Please read these terms carefully before submitting."

    # Duplicate question name disambiguated
    assert survey["pages"][1]["elements"][1]["name"] == "full_name_2"


