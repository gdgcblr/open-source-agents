"""Centralized token-efficient model policy and execution orchestrator."""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from agentrelay.config import Config, get_config
from agentrelay.evidence import EvidenceStore, redact_secrets
from agentrelay.guardrails import validate_report
from agentrelay.model_client import (
    BaseModelClient,
    ModelError,
    ModelResponse,
    ModelUnavailableError,
    ModelUsage,
    get_model_client,
)
from agentrelay.schemas import (
    Finding,
    Hypothesis,
    InvestigationReport,
)

# Tasks that must ALWAYS run deterministically with zero model calls
DETERMINISTIC_ONLY_TASKS: Set[str] = {
    "schema_validation",
    "evidence_validation",
    "diff_parsing",
    "static_risk_detection",
    "metric_calculation",
    "exact_commit_correlation",
    "report_formatting",
    "secret_redaction",
}

# Tasks that can legitimately benefit from model semantic reasoning if configured
SEMANTIC_TASKS: Set[str] = {
    "semantic_code_reasoning",
    "competing_hypothesis_comparison",
    "incident_summary_synthesis",
}


class ModelPolicy:
    """Enforces token-efficiency, safety bounds, deterministic priority, and transparent fallback."""

    def __init__(
        self,
        config: Optional[Config] = None,
        client: Optional[BaseModelClient] = None,
    ) -> None:
        self.config = config or get_config()
        self.client = client or get_model_client(self.config)
        self._cache: Dict[str, ModelResponse] = {}
        self.recorded_calls: List[Dict[str, Any]] = []

    def should_invoke_model(
        self,
        task_name: str,
        is_ambiguous: bool = False,
        force_semantic: bool = False,
    ) -> bool:
        """Centralized gating logic: strictly prefers deterministic execution."""
        # 1. Offline mode always disables model calling
        if self.config.offline_mode or self.config.model_provider == "offline":
            return False

        # 2. Deterministic-only tasks must NEVER call a model
        if task_name in DETERMINISTIC_ONLY_TASKS:
            return False

        # 3. For semantic tasks, only invoke if explicitly requested or ambiguous
        if task_name in SEMANTIC_TASKS:
            return force_semantic or is_ambiguous

        # Unknown or unspecified tasks default to deterministic (no model)
        return False

    def _compute_cache_key(self, prompt: str, system_prompt: Optional[str]) -> str:
        h = hashlib.sha256()
        h.update(self.config.model_name.encode("utf-8"))
        h.update((system_prompt or "").encode("utf-8"))
        h.update(prompt.encode("utf-8"))
        return h.hexdigest()

    def run_semantic_code_review(
        self,
        diff_snippet: str,
        deterministic_report: InvestigationReport,
        evidence_store: EvidenceStore,
    ) -> InvestigationReport:
        """Augment deterministic code review with bounded semantic model reasoning if policy allows."""
        if not self.should_invoke_model("semantic_code_reasoning", force_semantic=True):
            # Return pure deterministic report without model call
            deterministic_report.execution_metadata["model_invoked"] = False
            return deterministic_report

        system_instruction = (
            "You are a code security and reliability reviewer. Analyze the supplied git diff. "
            "Output JSON with a list of 'semantic_findings'. Every finding must have: "
            "'claim', 'severity', 'confidence', 'evidence_ids' (must match provided IDs), "
            "'explanation', and 'recommended_next_action'."
        )

        # Bound context: include only relevant evidence IDs
        prompt_data = {
            "diff": redact_secrets(diff_snippet[:3000]),
            "known_evidence_ids": list(evidence_store.known_ids),
        }
        prompt = json.dumps(prompt_data)
        cache_key = self._compute_cache_key(prompt, system_instruction)

        # Check cache
        if cache_key in self._cache:
            resp = self._cache[cache_key]
            resp.cached = True
        else:
            try:
                resp = self.client.generate(
                    prompt=prompt,
                    system_instruction=system_instruction,
                    expected_json_keys=["semantic_findings"],
                )
                self._cache[cache_key] = resp
            except (ModelError, ModelUnavailableError) as exc:
                # Transparent fallback to deterministic result
                deterministic_report.execution_metadata["model_invoked"] = False
                deterministic_report.execution_metadata["fallback_reason"] = str(exc)
                return deterministic_report

        self.recorded_calls.append(
            {
                "task": "semantic_code_reasoning",
                "model": resp.model_name,
                "latency_ms": resp.latency_ms,
                "usage": resp.usage.to_dict(),
            }
        )

        # Parse and validate response
        if resp.structured_data and isinstance(resp.structured_data.get("semantic_findings"), list):
            for item in resp.structured_data["semantic_findings"]:
                if isinstance(item, dict):
                    # Enforce citation validity: only keep if evidence IDs are known
                    eids = item.get("evidence_ids", [])
                    if eids and set(eids).issubset(evidence_store.known_ids):
                        try:
                            finding = Finding(
                                claim=str(item.get("claim", "")),
                                severity=str(item.get("severity", "medium")),
                                confidence=str(item.get("confidence", "low")),
                                evidence_ids=eids,
                                explanation=str(item.get("explanation", "")),
                                recommended_next_action=str(item.get("recommended_next_action", "Review")),
                            )
                            if not finding.validate(evidence_store.known_ids):
                                deterministic_report.findings.append(finding)
                        except Exception:
                            pass

        deterministic_report.execution_metadata["model_invoked"] = True
        deterministic_report.execution_metadata["model_usage"] = resp.usage.to_dict()
        return deterministic_report
