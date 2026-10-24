"""AgentRelay: Evidence-Driven AI Engineering Investigation Platform."""

__version__ = "0.1.0"

from agentrelay.code_review import run_deterministic_review
from agentrelay.config import Config, get_config
from agentrelay.correlation import correlate_review_and_incident
from agentrelay.evaluator import run_eval_suite
from agentrelay.evidence import EvidenceStore
from agentrelay.guardrails import require_valid_report, validate_report
from agentrelay.incident_investigator import run_incident_investigation
from agentrelay.model_policy import ModelPolicy
from agentrelay.schemas import (
    CorrelationLink,
    CorrelationReport,
    EvidenceRecord,
    Finding,
    Hypothesis,
    InvestigationReport,
)

__all__ = [
    "Config",
    "get_config",
    "EvidenceRecord",
    "Finding",
    "Hypothesis",
    "InvestigationReport",
    "CorrelationLink",
    "CorrelationReport",
    "EvidenceStore",
    "run_deterministic_review",
    "run_incident_investigation",
    "correlate_review_and_incident",
    "validate_report",
    "require_valid_report",
    "ModelPolicy",
    "run_eval_suite",
]
