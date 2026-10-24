import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from google import genai
from google.genai import types

from schemas import ContractDriftReport
from guardrails import (
    scan_for_secrets,
    scan_for_prompt_injection,
    validate_patch_output,
    GuardrailValidationError,
)

SYSTEM_INSTRUCTION = """
You are a Principal Cloud Architect and Application Security Engineer specializing in microservices, Spring Security / OAuth2, and OpenAPI 3.0 / API Gateway policies.

Your mission is dual-fold:
1. SCHEMA DRIFT: Identify breaking interface changes (field renames, type shifts, missing endpoints, status code changes).
2. SECURITY & POLICY DRIFT:
   - Extract security schemes (`components.securitySchemes`) and route-level `security` declarations from the OpenAPI spec.
   - Inspect backend controller methods for security annotations (e.g., `@PreAuthorize`, `@RolesAllowed`, `@Secured`, `@AuthenticationPrincipal`, or middleware).
   - If the spec marks an endpoint as requiring `BearerAuth` or specific scopes (e.g., `ROLE_ADMIN`, `read:users`) but the controller lacks authorization annotations, flag it as `CRITICAL` severity with `MISSING_AUTH_GUARD` or `MISSING_ROLE_SCOPE`.
   - If an endpoint handles PII/sensitive data and lacks authentication, flag `UNPROTECTED_SENSITIVE_DATA`.
   - Provide a `suggested_security_patch` demonstrating the exact backend security code needed to resolve the exposure.

Output must strictly adhere to the ContractDriftReport JSON schema.
"""


def analyze_drift(code_content: str, spec_content: str) -> ContractDriftReport:
    secrets = scan_for_secrets(code_content, "code_file") + scan_for_secrets(spec_content, "spec_file")
    if secrets:
        raise GuardrailValidationError(f"Secret Exfiltration Guardrail: {', '.join(secrets)}. Operation aborted.")

    scan_for_prompt_injection(code_content)
    scan_for_prompt_injection(spec_content)

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable is missing.")

    model_name = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    client = genai.Client(api_key=api_key)

    user_prompt = f"""
<analyzed_artifacts>
<backend_controller_code>
{code_content}
</backend_controller_code>

<openapi_specification>
{spec_content}
</openapi_specification>
</analyzed_artifacts>

Perform contract schema parity check and comprehensive API Gateway Security & Policy audit.
"""

    safety_settings = [
        types.SafetySetting(
            category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
            threshold=types.HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,
        ),
        types.SafetySetting(
            category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
            threshold=types.HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,
        ),
    ]

    response = client.models.generate_content(
        model=model_name,
        contents=user_prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            response_schema=ContractDriftReport,
            safety_settings=safety_settings,
            temperature=0.0,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )

    report = ContractDriftReport.model_validate_json(response.text)

    if report.suggested_spec_patch:
        is_valid, msg = validate_patch_output(report.suggested_spec_patch)
        if not is_valid:
            report.suggested_spec_patch = f"/* Guardrail Warning: {msg} */"

    return report