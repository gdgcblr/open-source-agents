"""Role-specific PatchProof agent modules and typed output contracts."""

from patchproof.agents.adjudicator import EvidenceAdjudicatorAgent
from patchproof.agents.adversarial_reviewer import AdversarialReviewerAgent
from patchproof.agents.base import (
    AdjudicatorOutput,
    AdversarialReviewerOutput,
    BaseAgentOutput,
    ChangeInvestigatorOutput,
    IntentAnalystOutput,
    TestCoverageOutput,
    VerificationAgentOutput,
    detect_prompt_injection_lines,
    is_prompt_injection_line,
)
from patchproof.agents.change_investigator import ChangeInvestigatorAgent
from patchproof.agents.intent_analyst import IntentAnalystAgent
from patchproof.agents.test_coverage import TestCoverageAgent
from patchproof.agents.verification_agent import VerificationAgent

__all__ = [
    "AdjudicatorOutput",
    "AdversarialReviewerAgent",
    "AdversarialReviewerOutput",
    "BaseAgentOutput",
    "ChangeInvestigatorAgent",
    "ChangeInvestigatorOutput",
    "EvidenceAdjudicatorAgent",
    "IntentAnalystAgent",
    "IntentAnalystOutput",
    "TestCoverageAgent",
    "TestCoverageOutput",
    "VerificationAgent",
    "VerificationAgentOutput",
    "detect_prompt_injection_lines",
    "is_prompt_injection_line",
]

