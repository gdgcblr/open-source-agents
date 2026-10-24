"""Test & Coverage Agent: inventories tests, inspects assertions, and flags coverage gaps."""

from __future__ import annotations

import ast
import time

from patchproof.agents.base import TestCoverageOutput
from patchproof.core.enums import (
    AgentStatus,
    Confidence,
    FindingCategory,
    FindingStatus,
    Severity,
)
from patchproof.core.ledger import EvidenceLedger
from patchproof.core.models import (
    SCHEMA_VERSION,
    ChangeMap,
    CheckRequest,
    CodeLocation,
    Finding,
    Requirement,
    TestInventoryItem,
    TestProposal,
)
from patchproof.ingestion.snapshot import ContextSnapshot
from patchproof.providers.base import LLMProvider, ProviderError


def _extract_test_assertions(
    func_node: ast.FunctionDef | ast.AsyncFunctionDef,
    source: str,
) -> list[str]:
    """Extract assertion and pytest.raises expressions from a test function AST."""
    assertions: list[str] = []
    for node in ast.walk(func_node):
        if isinstance(node, ast.Assert):
            seg = ast.get_source_segment(source, node)
            if seg:
                assertions.append(seg.strip())
        elif isinstance(node, ast.With):
            for item in node.items:
                seg = ast.get_source_segment(source, item.context_expr)
                if seg and "raises" in seg:
                    assertions.append(f"with {seg.strip()}")
    return assertions


class TestCoverageAgent:
    """Assesses whether requirements are exercised by existing tests and proposes focused checks."""

    name = "test_coverage_agent"

    def __init__(self, provider: LLMProvider | None = None) -> None:
        self._provider = provider

    def run(
        self,
        snapshot: ContextSnapshot,
        requirements: list[Requirement],
        change_map: ChangeMap,
        ledger: EvidenceLedger,
    ) -> TestCoverageOutput:
        start = time.perf_counter()
        warnings: list[str] = []
        evidence_ids = list(snapshot.test_evidence_ids.values())
        if not evidence_ids and snapshot.diff_evidence_id:
            evidence_ids.append(snapshot.diff_evidence_id)

        if self._provider is not None and self._provider.name != "none":
            try:
                return self._provider.generate_structured(
                    role=self.name,
                    system_prompt=(
                        "Inventory existing tests, link assertions to requirements, and report "
                        "TEST_GAP findings without claiming unverified functional defects."
                    ),
                    untrusted_context={
                        "test_files": list(snapshot.test_files.keys()),
                        "requirements": [r.model_dump() for r in requirements],
                        "evidence_ids": evidence_ids,
                    },
                    response_schema=TestCoverageOutput,
                )
            except ProviderError as exc:
                warnings.append(
                    f"Provider '{self._provider.name}' failed in {self.name} "
                    f"({exc}); used deterministic fallback."
                )

        inventory: list[TestInventoryItem] = []
        test_counter = 0

        for path, file_snap in sorted(snapshot.test_files.items()):
            tst_ev_id = snapshot.test_evidence_ids.get(path) or "E-001"
            try:
                tree = ast.parse(file_snap.content, filename=path)
            except SyntaxError as exc:
                warnings.append(f"SyntaxError in test file '{path}': {exc.msg}")
                continue

            for node in tree.body:
                is_test_fn = isinstance(
                    node, (ast.FunctionDef, ast.AsyncFunctionDef)
                ) and node.name.startswith("test")
                if is_test_fn:
                    assert isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                    test_counter += 1
                    test_id = f"T-{test_counter:03d}"
                    line_s = node.lineno
                    line_e = getattr(node, "end_lineno", line_s) or line_s
                    assertions = _extract_test_assertions(node, file_snap.content)
                    func_source = ast.get_source_segment(file_snap.content, node) or ""

                    covered_reqs: list[str] = []
                    for req in requirements:
                        req_lower = req.text.lower()
                        if "valueerror" in req_lower or "negative" in req_lower:
                            if any("ValueError" in a for a in assertions):
                                covered_reqs.append(req.requirement_id)
                        elif "fatal" in req_lower or "permanent" in req_lower:
                            if any("FatalClientError" in a for a in assertions) or (
                                "FatalClientError" in func_source and assertions
                            ):
                                covered_reqs.append(req.requirement_id)
                        elif any(
                            k in req_lower for k in ("at most", "limit", "max_retries")
                        ):
                            has_exhaustion_bound_assert = (
                                "AlwaysFails" in func_source
                                or "always_fail" in func_source
                                or "pytest.raises(TransientError" in func_source
                            ) and any(
                                ("call_count ==" in a or "attempts ==" in a or "calls ==" in a)
                                for a in assertions
                            )
                            if has_exhaustion_bound_assert:
                                covered_reqs.append(req.requirement_id)

                    inventory.append(
                        TestInventoryItem(
                            test_id=test_id,
                            path=path,
                            name=node.name,
                            line_start=line_s,
                            line_end=line_e,
                            assertions=assertions,
                            covered_requirement_ids=covered_reqs,
                            evidence_id=tst_ev_id,
                        )
                    )

        requirement_to_tests: dict[str, list[str]] = {r.requirement_id: [] for r in requirements}
        for item in inventory:
            for req_id in item.covered_requirement_ids:
                if req_id in requirement_to_tests:
                    requirement_to_tests[req_id].append(item.test_id)

        test_gap_findings: list[Finding] = []
        test_proposals: list[TestProposal] = []
        proposal_idx = 0
        gap_idx = 0

        for req in requirements:
            linked_tests = requirement_to_tests.get(req.requirement_id, [])
            if not linked_tests:
                gap_idx += 1
                proposal_idx += 1
                gap_ev_ids = list(evidence_ids) if evidence_ids else list(req.evidence_ids)
                locs = [
                    CodeLocation(path=p, line_start=1, line_end=max(1, s.line_count))
                    for p, s in snapshot.test_files.items()
                ]
                gap_status = (
                    FindingStatus.CONFIRMED
                    if snapshot.test_files
                    else FindingStatus.UNVERIFIED
                )
                test_gap_findings.append(
                    Finding(
                        finding_id=f"F-{200 + gap_idx:03d}",
                        category=FindingCategory.TEST_GAP,
                        severity=Severity.MEDIUM,
                        confidence=Confidence.HIGH,
                        status=gap_status,
                        title=f"Missing boundary test assertion for {req.requirement_id}",
                        description=(
                            f"Existing test suite does not contain an assertion verifying boundary "
                            f"behavior for requirement {req.requirement_id} ('{req.text}'). "
                            "A missing test is recorded as a TEST_GAP and is not by itself proof "
                            "of a functional defect."
                        ),
                        requirement_ids=[req.requirement_id],
                        evidence_ids=gap_ev_ids,
                        locations=locs,
                        recommended_action=(
                            f"Add a unit test that forces retry exhaustion at the exact boundary "
                            f"(e.g., max_retries=3 and max_retries=0) and asserts exact call count "
                            f"for {req.requirement_id}."
                        ),
                    )
                )
                req_slug = req.requirement_id.lower().replace("-", "_")
                test_proposals.append(
                    TestProposal(
                        proposal_id=f"TP-{proposal_idx:03d}",
                        requirement_id=req.requirement_id,
                        name=f"test_{req_slug}_boundary_exhaustion",
                        preconditions="Callable always raises TransientError; sleep is stubbed.",
                        input_summary=(
                            "Invoke retry_request(always_fails, max_retries=3) and max_retries=0."
                        ),
                        expected_outcome=(
                            "Raises TransientError after exactly 1 + max_retries total invocations "
                            "(4 calls for max_retries=3; 1 call for max_retries=0)."
                        ),
                        rationale=(
                            f"Directly exercises upper-bound invariant for {req.requirement_id}."
                        ),
                    )
                )

        all_req_ids = [r.requirement_id for r in requirements]
        primary_source = next(iter(snapshot.source_files.keys()), None)
        check_requests: list[CheckRequest] = [
            CheckRequest(
                check_id="C-001",
                name="static-ast-retry-bound-check",
                profile="static_ast_retry_bound",
                args=["--strict-bounds"],
                target_path=primary_source,
                requirement_ids=all_req_ids[:1] if all_req_ids else [],
                rationale="Deterministic static AST verification of retry loop upper bound.",
            ),
            CheckRequest(
                check_id="C-002",
                name="sandbox-pytest-suite",
                profile="sandbox_pytest",
                args=["-q"],
                target_path=next(iter(snapshot.test_files.keys()), None),
                requirement_ids=all_req_ids,
                rationale="Execute test suite inside isolated sandbox container if enabled.",
            ),
        ]

        if not snapshot.test_files:
            warnings.append("No test files were present in the repository snapshot.")

        duration_ms = int((time.perf_counter() - start) * 1000)
        summary = (
            f"Inventoried {len(inventory)} test(s); found {len(test_gap_findings)} test gap(s) "
            f"and proposed {len(test_proposals)} targeted test(s)."
        )

        return TestCoverageOutput(
            agent_name=self.name,
            schema_version=SCHEMA_VERSION,
            status=AgentStatus.SUCCEEDED,
            summary=summary,
            evidence_ids=evidence_ids,
            warnings=warnings,
            duration_ms=duration_ms,
            test_inventory=inventory,
            requirement_to_tests=requirement_to_tests,
            test_gap_findings=test_gap_findings,
            test_proposals=test_proposals,
            check_requests=check_requests,
        )
