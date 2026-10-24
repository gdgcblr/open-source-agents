"""Threat Modeling and cross-file attack-path correlation."""
from typing import List
from securepr.models import (
    AttackPathHypothesis,
    AttackPathStep,
    Finding,
    FindingCategory,
    STRIDECategory,
)


class ThreatCorrelationEngine:
    def correlate(self, findings: List[Finding]) -> List[AttackPathHypothesis]:
        hypotheses: List[AttackPathHypothesis] = []

        secrets = [f for f in findings if f.category == FindingCategory.SECRET]
        jwt_flaws = [f for f in findings if f.category == FindingCategory.JWT_AUTH]
        api_auth = [f for f in findings if f.category == FindingCategory.API_AUTHORIZATION]
        configs = [f for f in findings if f.category == FindingCategory.CONFIG]

        # Pattern 1: Leaked Secret or Token Flaw + Unprotected Endpoint -> Escalation of Privilege
        if (secrets or jwt_flaws) and api_auth:
            source = secrets[0] if secrets else jwt_flaws[0]
            target = api_auth[0]

            steps = [
                AttackPathStep(
                    step_number=1,
                    file_path=source.evidence[0].file_path,
                    action_or_state="Attacker acquires credential or exploits disabled signature check to forge user identity.",
                    associated_finding_id=source.id,
                ),
                AttackPathStep(
                    step_number=2,
                    file_path=target.evidence[0].file_path,
                    action_or_state="Attacker invokes unprotected mutation or object query without identity/ownership verification.",
                    associated_finding_id=target.id,
                ),
                AttackPathStep(
                    step_number=3,
                    file_path=target.evidence[0].file_path,
                    action_or_state="Database state modification or unauthorized data extraction across tenant boundary.",
                    associated_finding_id=target.id,
                ),
            ]

            hypotheses.append(
                AttackPathHypothesis(
                    id="HYP-AUTH-CHAIN-01",
                    title="Credential / Token Bypass leading to Unauthorized Object Access (BOLA)",
                    summary="Correlation of secret leakage/token flaw with missing endpoint authorization enables end-to-end compromise.",
                    stride=STRIDECategory.ELEVATION_OF_PRIVILEGE,
                    steps=steps,
                    requires_validation=True,
                )
            )

        # Pattern 2: Wildcard CORS + Unauthenticated Mutation -> Cross-Origin State Tampering
        cors_issues = [f for f in configs if "cors" in f.title.lower() or "cors" in f.description.lower()]
        if cors_issues and api_auth:
            hypotheses.append(
                AttackPathHypothesis(
                    id="HYP-CORS-TAMPER-02",
                    title="Cross-Site API Tampering via Overly Permissive CORS Policy",
                    summary="An external malicious website can execute API requests against an exposed route using an open CORS wildcard configuration.",
                    stride=STRIDECategory.TAMPERING,
                    steps=[
                        AttackPathStep(
                            step_number=1,
                            file_path=cors_issues[0].evidence[0].file_path,
                            action_or_state="Browser trusts third-party domain origin due to wildcard CORS.",
                            associated_finding_id=cors_issues[0].id,
                        ),
                        AttackPathStep(
                            step_number=2,
                            file_path=api_auth[0].evidence[0].file_path,
                            action_or_state="Malicious script executes state-modifying POST request to endpoint missing authorization.",
                            associated_finding_id=api_auth[0].id,
                        ),
                    ],
                    requires_validation=True,
                )
            )

        return hypotheses
