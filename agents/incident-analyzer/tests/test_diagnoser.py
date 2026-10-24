"""Tests for the diagnosis engine module."""

import os
import json
import tempfile

import pytest

from incident_analyzer.ast_indexer import index_codebase
from incident_analyzer.diagnoser import (
    correlate_with_spec,
    diagnose,
    extract_traceback_frames,
    _validate_fix_syntax,
    _build_context_for_llm,
    _parse_llm_response,
)
from incident_analyzer.models import (
    AffectedSymbol,
    CodebaseSpec,
    Diagnosis,
    IncidentInput,
    ModuleSpec,
    CodeSymbol,
    Severity,
    SuggestedFix,
    SymbolType,
)


# ── Fixtures ────────────────────────────────────────────────────────────


SAMPLE_TRACEBACK = """\
Traceback (most recent call last):
  File "app.py", line 42, in process_data
    result = transform(data)
  File "utils.py", line 15, in transform
    return data.split(",")
AttributeError: 'NoneType' object has no attribute 'split'
"""

SAMPLE_TRACEBACK_WITH_SECRETS = """\
Traceback (most recent call last):
  File "/Users/johndoe/projects/app.py", line 42, in connect_db
    conn = connect(url="postgresql://admin:secret@localhost/mydb")
  File "db.py", line 10, in connect
    raise ConnectionError("Failed")
ConnectionError: Failed to connect (api_key=sk-1234567890abcdefghijklmnop)
"""


@pytest.fixture
def sample_spec() -> CodebaseSpec:
    """Create a minimal CodebaseSpec for testing."""
    return CodebaseSpec(
        root_path="/tmp/test-project",
        modules=[
            ModuleSpec(
                file_path="app.py",
                imports=["from utils import transform"],
                symbols=[
                    CodeSymbol(
                        name="process_data",
                        symbol_type=SymbolType.FUNCTION,
                        file_path="app.py",
                        line_start=35,
                        line_end=50,
                        signature="def process_data(data: str) -> list",
                        docstring="Process raw data into structured output.",
                        calls=["transform", "validate"],
                        source_snippet="def process_data(data: str) -> list:\n"
                                       '    result = transform(data)\n'
                                       "    return result",
                    ),
                    CodeSymbol(
                        name="validate",
                        symbol_type=SymbolType.FUNCTION,
                        file_path="app.py",
                        line_start=55,
                        line_end=65,
                        signature="def validate(data) -> bool",
                        docstring="Validate input data.",
                        calls=["isinstance"],
                        source_snippet="def validate(data) -> bool:\n"
                                       "    return isinstance(data, str)",
                    ),
                ],
            ),
            ModuleSpec(
                file_path="utils.py",
                imports=[],
                symbols=[
                    CodeSymbol(
                        name="transform",
                        symbol_type=SymbolType.FUNCTION,
                        file_path="utils.py",
                        line_start=10,
                        line_end=20,
                        signature="def transform(data: str) -> list[str]",
                        docstring="Transform data by splitting on commas.",
                        calls=["split"],
                        source_snippet='def transform(data: str) -> list[str]:\n'
                                       '    return data.split(",")',
                    ),
                ],
            ),
        ],
        total_symbols=3,
        total_files=2,
    )


@pytest.fixture
def sample_project_dir(tmp_path):
    """Create a temporary project for end-to-end testing."""
    (tmp_path / "app.py").write_text(
        'def process_data(data: str) -> list:\n'
        '    """Process raw data."""\n'
        '    result = transform(data)\n'
        '    return result\n'
    )
    (tmp_path / "utils.py").write_text(
        'def transform(data: str) -> list[str]:\n'
        '    """Transform data by splitting."""\n'
        '    return data.split(",")\n'
    )
    return tmp_path


# ── extract_traceback_frames tests ─────────────────────────────────────


def test_extract_traceback_frames_basic():
    """Test extracting frames from a standard Python traceback."""
    frames = extract_traceback_frames(SAMPLE_TRACEBACK)
    assert len(frames) == 2
    assert frames[0]["file"] == "app.py"
    assert frames[0]["line"] == 42
    assert frames[0]["function"] == "process_data"
    assert frames[1]["file"] == "utils.py"
    assert frames[1]["line"] == 15
    assert frames[1]["function"] == "transform"


def test_extract_traceback_frames_with_code():
    """Test that code lines are captured from tracebacks."""
    frames = extract_traceback_frames(SAMPLE_TRACEBACK)
    assert "code" in frames[0]
    assert "transform" in frames[0]["code"]


def test_extract_traceback_frames_no_traceback():
    """Test with input that has no traceback."""
    frames = extract_traceback_frames("Just a normal log line.\nAnother line.")
    assert len(frames) == 0


def test_extract_traceback_frames_multiple_tracebacks():
    """Test extracting from multiple tracebacks in one log."""
    log = SAMPLE_TRACEBACK + "\n---\n" + SAMPLE_TRACEBACK
    frames = extract_traceback_frames(log)
    assert len(frames) == 4


# ── correlate_with_spec tests ──────────────────────────────────────────


def test_correlate_with_spec_matches_function_name(sample_spec):
    """Test that frames are correlated by function name."""
    frames = extract_traceback_frames(SAMPLE_TRACEBACK)
    affected = correlate_with_spec(frames, sample_spec)
    affected_names = [s.name for s in affected]
    assert "process_data" in affected_names
    assert "transform" in affected_names


def test_correlate_with_spec_matches_by_line_range(sample_spec):
    """Test correlation by line range when function name doesn't match."""
    frames = [{"file": "app.py", "line": 40, "function": "unknown_func"}]
    affected = correlate_with_spec(frames, sample_spec)
    # Line 40 falls within process_data (35-50)
    affected_names = [s.name for s in affected]
    assert "process_data" in affected_names


def test_correlate_with_spec_no_match(sample_spec):
    """Test that unmatched frames produce empty results."""
    frames = [{"file": "nonexistent.py", "line": 99, "function": "foo"}]
    affected = correlate_with_spec(frames, sample_spec)
    assert len(affected) == 0


def test_correlate_with_spec_deduplicates(sample_spec):
    """Test that duplicate symbol matches are deduplicated."""
    frames = [
        {"file": "app.py", "line": 42, "function": "process_data"},
        {"file": "app.py", "line": 45, "function": "process_data"},
    ]
    affected = correlate_with_spec(frames, sample_spec)
    process_data_count = sum(1 for s in affected if s.name == "process_data")
    assert process_data_count == 1


# ── _validate_fix_syntax tests ─────────────────────────────────────────


def test_validate_fix_syntax_valid():
    """Test that valid Python code passes validation."""
    fix = SuggestedFix(
        file_path="test.py",
        original_code="x = 1",
        fixed_code="x = 1 + 1",
        explanation="Increment x",
    )
    _validate_fix_syntax(fix)
    assert "⚠️" not in fix.explanation


def test_validate_fix_syntax_invalid():
    """Test that invalid Python code gets flagged but doesn't raise."""
    fix = SuggestedFix(
        file_path="test.py",
        original_code="x = 1",
        fixed_code="def broken(:\n    pass",
        explanation="Fix function",
    )
    _validate_fix_syntax(fix)  # Should not raise
    assert "⚠️" in fix.explanation


def test_generate_unified_diff():
    """Test generating a git-compatible unified diff."""
    from incident_analyzer.diagnoser import generate_unified_diff

    orig = "def add(a, b):\n    return a + b\n"
    fixed = "def add(a, b):\n    # add docstring\n    return a + b\n"
    diff = generate_unified_diff("math.py", orig, fixed)
    assert "--- a/math.py" in diff
    assert "+++ b/math.py" in diff
    assert "+    # add docstring" in diff


# ── _build_context_for_llm tests ──────────────────────────────────────


def test_build_context_includes_relevant_symbols(sample_spec):
    """Test that LLM context includes affected and caller symbols."""
    incident = IncidentInput(log_text=SAMPLE_TRACEBACK)
    affected = [
        AffectedSymbol(
            name="transform",
            file_path="utils.py",
            line_start=10,
            line_end=20,
            relevance="Traceback frame",
        )
    ]
    context = _build_context_for_llm(sample_spec, incident, affected, SAMPLE_TRACEBACK)
    assert "transform" in context
    # process_data calls transform, so it should also appear
    assert "process_data" in context


def test_build_context_includes_actual_expected(sample_spec):
    """Test that actual/expected output is included in context."""
    incident = IncidentInput(
        log_text="Error occurred",
        actual_output="[1, 2, 3]",
        expected_output="[1, 2, 3, 4]",
    )
    context = _build_context_for_llm(sample_spec, incident, [], "Error occurred")
    assert "Actual Output" in context
    assert "[1, 2, 3]" in context
    assert "Expected Output" in context
    assert "[1, 2, 3, 4]" in context


def test_build_context_includes_developer_context(sample_spec):
    """Test that developer context is included."""
    incident = IncidentInput(
        log_text="Error",
        context="This started happening after the refactor",
    )
    context = _build_context_for_llm(sample_spec, incident, [], "Error")
    assert "Developer Context" in context
    assert "refactor" in context


# ── _parse_llm_response tests ─────────────────────────────────────────


def test_parse_llm_response_valid_json():
    """Test parsing a valid LLM JSON response."""
    response = json.dumps({
        "root_cause": "NoneType passed to transform",
        "severity": "medium",
        "affected_symbols": [
            {
                "name": "transform",
                "file_path": "utils.py",
                "line_start": 10,
                "line_end": 20,
                "relevance": "Direct crash site",
            }
        ],
        "suggested_fixes": [
            {
                "file_path": "app.py",
                "original_code": "result = transform(data)",
                "fixed_code": "result = transform(data) if data else []",
                "explanation": "Add None check",
            }
        ],
        "prevention_tips": ["Add input validation"],
        "confidence": 0.9,
    })
    diagnosis = _parse_llm_response(response, [])
    assert diagnosis.root_cause == "NoneType passed to transform"
    assert diagnosis.severity == Severity.MEDIUM
    assert len(diagnosis.suggested_fixes) == 1
    assert diagnosis.confidence == 0.9


def test_parse_llm_response_with_code_fences():
    """Test parsing JSON wrapped in markdown code fences."""
    response = '```json\n{"root_cause": "test", "severity": "low", "affected_symbols": [], "suggested_fixes": [], "prevention_tips": [], "confidence": 0.5}\n```'
    diagnosis = _parse_llm_response(response, [])
    assert diagnosis.root_cause == "test"
    assert diagnosis.severity == Severity.LOW


def test_parse_llm_response_invalid_json():
    """Test fallback when LLM returns invalid JSON."""
    response = "This is not JSON at all, just plain text analysis."
    diagnosis = _parse_llm_response(response, [])
    assert diagnosis.confidence == 0.3
    assert "raw" in diagnosis.root_cause.lower() or "LLM" in diagnosis.root_cause


# ── Mock mode end-to-end tests ────────────────────────────────────────


def test_diagnose_mock_mode(sample_spec):
    """Test full diagnosis pipeline in mock mode."""
    incident = IncidentInput(log_text=SAMPLE_TRACEBACK)
    diagnosis = diagnose(spec=sample_spec, incident=incident, mock=True)

    assert isinstance(diagnosis, Diagnosis)
    assert "MOCK MODE" in diagnosis.root_cause
    assert diagnosis.severity == Severity.MEDIUM  # AttributeError → MEDIUM
    assert len(diagnosis.affected_symbols) > 0
    assert diagnosis.confidence == 0.5


def test_diagnose_mock_mode_detects_error_type(sample_spec):
    """Test that mock mode correctly detects specific error types."""
    traceback_import = """\
Traceback (most recent call last):
  File "app.py", line 1, in <module>
    import nonexistent_module
ModuleNotFoundError: No module named 'nonexistent_module'
"""
    incident = IncidentInput(log_text=traceback_import)
    diagnosis = diagnose(spec=sample_spec, incident=incident, mock=True)
    assert diagnosis.severity == Severity.HIGH


def test_diagnose_mock_mode_with_actual_expected(sample_spec):
    """Test mock diagnosis with actual vs expected output."""
    incident = IncidentInput(
        log_text=SAMPLE_TRACEBACK,
        actual_output="None",
        expected_output='["a", "b", "c"]',
    )
    diagnosis = diagnose(spec=sample_spec, incident=incident, mock=True)
    assert isinstance(diagnosis, Diagnosis)


def test_diagnose_sanitizes_secrets(sample_spec):
    """Test that secrets in logs are sanitized before diagnosis."""
    incident = IncidentInput(log_text=SAMPLE_TRACEBACK_WITH_SECRETS)
    diagnosis = diagnose(spec=sample_spec, incident=incident, mock=True)
    # The diagnosis should not contain the raw secret
    diagnosis_json = diagnosis.model_dump_json()
    assert "sk-1234567890abcdefghijklmnop" not in diagnosis_json
    assert "admin:secret" not in diagnosis_json


# ── End-to-end with real indexing ─────────────────────────────────────


def test_end_to_end_index_and_diagnose(sample_project_dir):
    """Test full pipeline: index a real project, then diagnose."""
    spec = index_codebase(str(sample_project_dir))
    assert spec.total_files == 2
    assert spec.total_symbols >= 2

    traceback = """\
Traceback (most recent call last):
  File "app.py", line 3, in process_data
    result = transform(data)
  File "utils.py", line 3, in transform
    return data.split(",")
AttributeError: 'NoneType' object has no attribute 'split'
"""
    incident = IncidentInput(
        log_text=traceback,
        actual_output="AttributeError raised",
        expected_output='["a", "b"]',
    )

    diagnosis = diagnose(spec=spec, incident=incident, mock=True)
    assert isinstance(diagnosis, Diagnosis)
    assert len(diagnosis.affected_symbols) > 0
    assert diagnosis.severity in [Severity.MEDIUM, Severity.HIGH]
