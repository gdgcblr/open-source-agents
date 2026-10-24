
from emergency_dispatch.guardrails.input_validation import parse_scenario
from emergency_dispatch.guardrails.output_validation import validate_recommendation
from emergency_dispatch.hospital_matcher import match_hospitals
from emergency_dispatch.models import ToolResult
from emergency_dispatch.optimizer import optimize_dispatch


def run_dispatch_agent(scenario: dict) -> ToolResult:
    """Run the deterministic emergency-dispatch decision-support workflow.

    This workflow produces recommendations only. A human dispatcher
    must review every recommendation before taking action.
    """
    try:
        incident, ambulances, hospitals = parse_scenario(scenario)
    except (ValueError, TypeError, KeyError) as exc:
        return ToolResult(
            success=False,
            errors=(f"Invalid scenario: {exc}",),
        )

    recommendation = optimize_dispatch(incident, ambulances)

    validation_errors = validate_recommendation(recommendation)
    if validation_errors:
        return ToolResult(
            success=False,
            errors=tuple(validation_errors),
            warnings=("The recommendation was rejected by output validation.",),
        )

    eligible_hospitals = match_hospitals(incident, hospitals)

    warnings = list(recommendation.warnings)

    if not eligible_hospitals:
        warnings.append(
            "No eligible hospital was found using the supplied capability "
            "requirements and capacity data."
        )

    result = {
        "recommendation": recommendation,
        "eligible_hospitals": eligible_hospitals,
    }

    return ToolResult(
        success=True,
        data=result,
        warnings=tuple(warnings),
    )
