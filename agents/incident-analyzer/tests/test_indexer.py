"""Tests for the AST indexer module."""

import ast
import os
import tempfile
import json

import pytest

from incident_analyzer.ast_indexer import (
    index_file,
    index_codebase,
    save_spec,
    load_spec,
    _reconstruct_signature,
    _extract_calls,
    _extract_decorators,
)
from incident_analyzer.models import SymbolType


# ── Fixtures ────────────────────────────────────────────────────────────


SAMPLE_MODULE = '''\
"""A sample module for testing the AST indexer."""

import os
from pathlib import Path


def greet(name: str, excited: bool = False) -> str:
    """Return a greeting message."""
    msg = f"Hello, {name}!"
    if excited:
        msg = msg.upper()
    print(msg)
    return msg


def add(a: int, b: int = 0) -> int:
    """Add two numbers."""
    return a + b


class Calculator:
    """A simple calculator class."""

    def __init__(self, initial: float = 0.0):
        """Initialize the calculator."""
        self.value = initial

    def multiply(self, x: float, y: float) -> float:
        """Multiply two numbers."""
        result = x * y
        self.value = result
        return result

    async def fetch_rate(self, currency: str) -> float:
        """Fetch an exchange rate (async stub)."""
        return 1.0
'''


SYNTAX_ERROR_MODULE = '''\
def broken(
    # missing closing paren and colon
'''


@pytest.fixture
def sample_project(tmp_path):
    """Create a temporary project with sample Python files."""
    # Main module
    (tmp_path / "app.py").write_text(SAMPLE_MODULE)

    # Sub-package
    pkg = tmp_path / "utils"
    pkg.mkdir()
    (pkg / "__init__.py").write_text('"""Utils package."""\n')
    (pkg / "helpers.py").write_text(
        'def helper_func(x):\n    """A helper."""\n    return x + 1\n'
    )

    # File with syntax error
    (tmp_path / "broken.py").write_text(SYNTAX_ERROR_MODULE)

    # Excluded directory
    venv = tmp_path / ".venv"
    venv.mkdir()
    (venv / "should_skip.py").write_text("# should not be indexed\n")

    return tmp_path


# ── index_file tests ───────────────────────────────────────────────────


def test_index_file_extracts_functions(sample_project):
    """Test that top-level functions are correctly extracted."""
    spec = index_file(str(sample_project / "app.py"), str(sample_project))
    func_names = [s.name for s in spec.symbols if s.symbol_type == SymbolType.FUNCTION]
    assert "greet" in func_names
    assert "add" in func_names


def test_index_file_extracts_classes(sample_project):
    """Test that classes and their methods are extracted."""
    spec = index_file(str(sample_project / "app.py"), str(sample_project))
    class_symbols = [s for s in spec.symbols if s.symbol_type == SymbolType.CLASS]
    assert len(class_symbols) == 1
    assert class_symbols[0].name == "Calculator"

    method_names = [s.name for s in spec.symbols if s.symbol_type == SymbolType.METHOD]
    assert "__init__" in method_names
    assert "multiply" in method_names
    assert "fetch_rate" in method_names


def test_index_file_extracts_imports(sample_project):
    """Test that import statements are captured."""
    spec = index_file(str(sample_project / "app.py"), str(sample_project))
    assert "import os" in spec.imports
    assert "from pathlib import Path" in spec.imports


def test_index_file_extracts_docstrings(sample_project):
    """Test that module and function docstrings are captured."""
    spec = index_file(str(sample_project / "app.py"), str(sample_project))
    assert spec.module_docstring == "A sample module for testing the AST indexer."

    greet = [s for s in spec.symbols if s.name == "greet"][0]
    assert greet.docstring == "Return a greeting message."


def test_index_file_extracts_signatures(sample_project):
    """Test that function signatures are reconstructed accurately."""
    spec = index_file(str(sample_project / "app.py"), str(sample_project))
    greet = [s for s in spec.symbols if s.name == "greet"][0]
    assert "name: str" in greet.signature
    assert "excited: bool=False" in greet.signature
    assert "-> str" in greet.signature


def test_index_file_extracts_calls(sample_project):
    """Test that function calls within a body are extracted."""
    spec = index_file(str(sample_project / "app.py"), str(sample_project))
    greet = [s for s in spec.symbols if s.name == "greet"][0]
    assert "print" in greet.calls
    assert "upper" in greet.calls


def test_index_file_extracts_source_snippet(sample_project):
    """Test that source snippets are captured."""
    spec = index_file(str(sample_project / "app.py"), str(sample_project))
    greet = [s for s in spec.symbols if s.name == "greet"][0]
    assert "def greet" in greet.source_snippet
    assert "Hello" in greet.source_snippet


def test_index_file_handles_syntax_error(sample_project):
    """Test that files with syntax errors are handled gracefully."""
    spec = index_file(str(sample_project / "broken.py"), str(sample_project))
    assert spec.file_path == "broken.py"
    assert len(spec.symbols) == 0


def test_index_file_relative_paths(sample_project):
    """Test that file paths are relative to root."""
    spec = index_file(str(sample_project / "app.py"), str(sample_project))
    assert spec.file_path == "app.py"

    spec2 = index_file(
        str(sample_project / "utils" / "helpers.py"), str(sample_project)
    )
    assert spec2.file_path == os.path.join("utils", "helpers.py")


# ── index_codebase tests ──────────────────────────────────────────────


def test_index_codebase_finds_all_files(sample_project):
    """Test that all Python files are indexed."""
    spec = index_codebase(str(sample_project))
    file_paths = [m.file_path for m in spec.modules]
    assert "app.py" in file_paths
    assert os.path.join("utils", "__init__.py") in file_paths
    assert os.path.join("utils", "helpers.py") in file_paths
    assert "broken.py" in file_paths


def test_index_codebase_excludes_venv(sample_project):
    """Test that excluded directories are skipped."""
    spec = index_codebase(str(sample_project))
    file_paths = [m.file_path for m in spec.modules]
    for fp in file_paths:
        assert ".venv" not in fp


def test_index_codebase_counts(sample_project):
    """Test that total_files and total_symbols are correct."""
    spec = index_codebase(str(sample_project))
    assert spec.total_files == 4  # app.py, __init__.py, helpers.py, broken.py
    assert spec.total_symbols > 0


def test_find_symbol(sample_project):
    """Test the find_symbol method on CodebaseSpec."""
    spec = index_codebase(str(sample_project))
    results = spec.find_symbol("greet")
    assert len(results) == 1
    assert results[0].name == "greet"


def test_find_symbols_in_file(sample_project):
    """Test finding symbols in a specific file."""
    spec = index_codebase(str(sample_project))
    symbols = spec.find_symbols_in_file("app.py")
    names = [s.name for s in symbols]
    assert "greet" in names
    assert "Calculator" in names


# ── save/load round-trip tests ────────────────────────────────────────


def test_save_and_load_spec(sample_project, tmp_path):
    """Test that specs survive a save/load round-trip."""
    spec = index_codebase(str(sample_project))
    spec_path = str(tmp_path / "test-spec.json")

    save_spec(spec, spec_path)
    assert os.path.exists(spec_path)

    loaded = load_spec(spec_path)
    assert loaded.total_files == spec.total_files
    assert loaded.total_symbols == spec.total_symbols
    assert len(loaded.modules) == len(spec.modules)


def test_saved_spec_is_valid_json(sample_project, tmp_path):
    """Test that the saved spec file is valid JSON."""
    spec = index_codebase(str(sample_project))
    spec_path = str(tmp_path / "test-spec.json")
    save_spec(spec, spec_path)

    with open(spec_path) as f:
        data = json.load(f)
    assert "root_path" in data
    assert "modules" in data


def test_generate_spec_markdown(sample_project):
    """Test generating human-readable Markdown spec from CodebaseSpec."""
    from incident_analyzer.ast_indexer import generate_spec_markdown

    spec = index_codebase(str(sample_project))
    md = generate_spec_markdown(spec)
    assert "# Codebase Specification" in md
    assert "Total Files" in md
    assert "greet" in md
    assert "Calculator" in md


# ── Helper function tests ─────────────────────────────────────────────


def test_reconstruct_signature_simple():
    """Test signature reconstruction for a simple function."""
    source = "def foo(a: int, b: str = 'hello') -> bool: pass"
    tree = ast.parse(source)
    func = tree.body[0]
    sig = _reconstruct_signature(func)
    assert "def foo" in sig
    assert "a: int" in sig
    assert "b: str='hello'" in sig
    assert "-> bool" in sig


def test_reconstruct_signature_async():
    """Test signature reconstruction for async functions."""
    source = "async def bar(x): pass"
    tree = ast.parse(source)
    func = tree.body[0]
    sig = _reconstruct_signature(func)
    assert sig.startswith("async def bar")


def test_reconstruct_signature_kwargs():
    """Test signature reconstruction with *args and **kwargs."""
    source = "def baz(*args, key=True, **kwargs): pass"
    tree = ast.parse(source)
    func = tree.body[0]
    sig = _reconstruct_signature(func)
    assert "*args" in sig
    assert "**kwargs" in sig
    assert "key=True" in sig


def test_extract_calls_simple():
    """Test call extraction from a function body."""
    source = "def f():\n    print('hello')\n    len([1,2])\n    x.append(1)"
    tree = ast.parse(source)
    calls = _extract_calls(tree.body[0])
    assert "print" in calls
    assert "len" in calls
    assert "append" in calls


def test_extract_decorators():
    """Test decorator extraction."""
    source = "@staticmethod\n@my_decorator\ndef f(): pass"
    tree = ast.parse(source)
    decorators = _extract_decorators(tree.body[0])
    assert "staticmethod" in decorators
    assert "my_decorator" in decorators
