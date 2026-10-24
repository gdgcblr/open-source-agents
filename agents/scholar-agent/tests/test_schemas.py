"""
tests/test_schemas.py - Unit tests for data contract enforcement
"""
import pytest
from pydantic import ValidationError
from schemas import ResearchPaperArtifacts, ExtractedTable

def test_valid_schema_initialization():
    payload = {
        "title": "ReAct: Synergizing Reasoning and Acting",
        "authors": "Yao et al.",
        "executive_summary": "A framework combining reasoning traces and action execution.",
        "key_insights": ["Combines CoT with tool execution", "Reduces hallucination rates"],
        "limitations_and_tradeoffs": ["Requires LLM tool-calling tokens"],
        "comparative_table": {
            "title": "Benchmark Results",
            "headers": ["Method", "HotpotQA"],
            "rows": [["Standard CoT", "34.1"], ["ReAct", "43.2"]]
        },
        "diagram_mermaid": "flowchart TD\n A[Thought] --> B[Act]"
    }
    artifact = ResearchPaperArtifacts(**payload)
    assert artifact.title == "ReAct: Synergizing Reasoning and Acting"
    assert len(artifact.comparative_table.rows) == 2

def test_rejects_missing_required_fields():
    # Omitting required comparative_table
    invalid_payload = {
        "title": "Paper Title",
        "executive_summary": "Summary text",
        "key_insights": ["Insight 1"]
    }
    with pytest.raises(ValidationError):
        ResearchPaperArtifacts(**invalid_payload)