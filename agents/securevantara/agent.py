"""Google Agent Development Kit (ADK) entry point for Securevantara.

Exports root_agent for the ADK CLI:
- Run locally with Web UI: `adk web agents/`
- Run from terminal: `adk run agents/securevantara "Review examples/source"`
"""
from .securevantara.adk_agent import (
    get_remediation_guidance,
    read_source_file,
    root_agent,
    run_ast_scan,
    run_full_security_review,
    run_with_adk,
    validate_finding_evidence,
)

__all__ = [
    "root_agent",
    "run_with_adk",
    "run_ast_scan",
    "read_source_file",
    "validate_finding_evidence",
    "get_remediation_guidance",
    "run_full_security_review",
]


