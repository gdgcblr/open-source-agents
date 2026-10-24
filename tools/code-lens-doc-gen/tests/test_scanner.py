"""
Tests for the CodeLens scanner and analyzer modules.

These tests verify the local-only components (no LLM calls required).
Run with: pytest tests/test_scanner.py -v
"""

import os
import sys
import tempfile
import textwrap
from pathlib import Path

# Ensure package root is in sys.path
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from codelens.config import Config, load_config, validate_config
from codelens.scanner import scan_codebase, format_file_tree, _is_text_file, _read_file_safe
from codelens.analyzer import analyze_file, analyze_codebase, condense_for_llm


# =============================================================================
# Config Tests
# =============================================================================

class TestConfig:
    def test_default_config(self):
        config = Config()
        assert config.gemini_model == "gemini-3.8-flash"
        assert config.max_file_size == 524288
        assert ".git" in config.ignore_dirs

    def test_validate_missing_api_key(self):
        config = Config(gemini_api_key="")
        errors = validate_config(config)
        assert len(errors) == 1
        assert "GEMINI_API_KEY" in errors[0]

    def test_validate_placeholder_api_key(self):
        config = Config(gemini_api_key="your_gemini_api_key_here")
        errors = validate_config(config)
        assert len(errors) == 1

    def test_validate_real_api_key(self):
        config = Config(gemini_api_key="mock-valid-api-key-for-testing")
        errors = validate_config(config)
        assert len(errors) == 0


# =============================================================================
# Scanner Tests
# =============================================================================

class TestScanner:
    def _create_temp_project(self):
        """Create a temporary project structure for testing."""
        tmpdir = tempfile.mkdtemp()

        # Create a Python file
        py_dir = os.path.join(tmpdir, "src")
        os.makedirs(py_dir)

        with open(os.path.join(py_dir, "main.py"), "w") as f:
            f.write(textwrap.dedent('''\
                """Main module docstring."""

                import os


                class MyApp:
                    """The main application class."""

                    def __init__(self, name: str):
                        self.name = name

                    def run(self) -> None:
                        """Run the application."""
                        print(f"Running {self.name}")

                    def _internal_method(self):
                        """Private helper."""
                        pass


                def public_function(x: int, y: int) -> int:
                    """Add two numbers."""
                    return x + y


                def _private_helper():
                    """Internal helper function."""
                    pass
            '''))

        # Create a config file
        with open(os.path.join(tmpdir, "config.yaml"), "w") as f:
            f.write("name: test-project\nversion: 1.0\nport: 8080\n")

        # Create a README
        with open(os.path.join(tmpdir, "README.md"), "w") as f:
            f.write("# Test Project\n\nThis is a test.\n")

        # Create a .gitignore that should be ignored
        os.makedirs(os.path.join(tmpdir, ".git"))

        return tmpdir

    def test_scan_codebase(self):
        tmpdir = self._create_temp_project()
        config = Config()

        result = scan_codebase(tmpdir, config)

        assert result["total_files"] > 0
        assert result["total_lines"] > 0
        assert isinstance(result["languages"], dict)
        assert isinstance(result["files"], list)

        # Check that .git directory was skipped
        paths = [f["path"] for f in result["files"]]
        assert not any(".git" in p for p in paths)

    def test_scan_detects_languages(self):
        tmpdir = self._create_temp_project()
        config = Config()

        result = scan_codebase(tmpdir, config)

        assert "python" in result["languages"]

    def test_scan_categorizes_files(self):
        tmpdir = self._create_temp_project()
        config = Config()

        result = scan_codebase(tmpdir, config)

        categories = {f["path"]: f["category"] for f in result["files"]}

        # src/main.py should be "source"
        assert categories.get("src/main.py") == "source"

    def test_format_file_tree(self):
        tree = {
            "src": {
                "main.py": None,
                "utils.py": None,
            },
            "README.md": None,
        }

        output = format_file_tree(tree)
        assert "src" in output
        assert "main.py" in output
        assert "README.md" in output

    def test_is_text_file(self):
        # Create a text file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("Hello, world!")
            text_path = f.name

        assert _is_text_file(text_path) is True

        # Create a binary file
        with tempfile.NamedTemporaryFile(mode="wb", suffix=".bin", delete=False) as f:
            f.write(b"\x00\x01\x02\x03\xff\xfe")
            bin_path = f.name

        assert _is_text_file(bin_path) is False

        os.unlink(text_path)
        os.unlink(bin_path)


# =============================================================================
# Analyzer Tests
# =============================================================================

class TestAnalyzer:
    def test_analyze_python_file(self):
        file_info = {
            "path": "test.py",
            "language": "python",
            "category": "source",
            "line_count": 20,
            "content": textwrap.dedent('''\
                """Module docstring."""

                class Foo:
                    """Foo class."""

                    def bar(self, x: int) -> str:
                        """Bar method."""
                        return str(x)

                def baz(a, b):
                    """Top-level function."""
                    return a + b
            '''),
        }

        result = analyze_file(file_info)

        assert result["module_docstring"] == "Module docstring."
        assert len(result["classes"]) == 1
        assert result["classes"][0]["name"] == "Foo"
        assert result["classes"][0]["docstring"] == "Foo class."
        assert len(result["classes"][0]["methods"]) == 1
        assert result["classes"][0]["methods"][0]["name"] == "bar"
        assert len(result["functions"]) == 1
        assert result["functions"][0]["name"] == "baz"

    def test_analyze_python_private_detection(self):
        file_info = {
            "path": "test.py",
            "language": "python",
            "category": "source",
            "line_count": 10,
            "content": textwrap.dedent('''\
                class _InternalClass:
                    pass

                def _private_func():
                    pass

                def public_func():
                    pass
            '''),
        }

        result = analyze_file(file_info)

        assert result["classes"][0]["is_private"] is True
        private_funcs = [f for f in result["functions"] if f["is_private"]]
        public_funcs = [f for f in result["functions"] if not f["is_private"]]
        assert len(private_funcs) == 1
        assert len(public_funcs) == 1

    def test_analyze_empty_file(self):
        file_info = {
            "path": "empty.py",
            "language": "python",
            "category": "source",
            "line_count": 0,
            "content": "",
        }

        result = analyze_file(file_info)
        assert result["classes"] == []
        assert result["functions"] == []

    def test_analyze_config_file(self):
        file_info = {
            "path": "config.json",
            "language": "json",
            "category": "config",
            "line_count": 5,
            "content": '{\n  "name": "test",\n  "version": "1.0",\n  "port": 8080\n}',
        }

        result = analyze_file(file_info)
        assert "name" in result["config_keys"]
        assert "version" in result["config_keys"]

    def test_condense_for_llm(self):
        analyses = [
            {
                "path": "main.py",
                "language": "python",
                "category": "source",
                "module_docstring": "Main module",
                "classes": [
                    {
                        "name": "App",
                        "docstring": "Application class",
                        "methods": [],
                        "bases": [],
                        "is_private": False,
                    }
                ],
                "functions": [
                    {
                        "name": "run",
                        "docstring": "Run the app",
                        "args": [],
                        "return_type": "",
                        "is_private": False,
                        "is_async": False,
                    }
                ],
                "imports": ["os", "sys"],
                "exports": [],
                "config_keys": [],
            }
        ]

        condensed = condense_for_llm(analyses)

        assert "main.py" in condensed
        assert "App" in condensed
        assert "run" in condensed
        assert isinstance(condensed, str)
        assert len(condensed) > 0


if __name__ == "__main__":
    import inspect

    passed = 0
    failed = 0
    test_classes = [TestConfig, TestScanner, TestAnalyzer]

    print("Running CodeLens local tests...")
    for cls in test_classes:
        instance = cls()
        for attr_name in dir(instance):
            if attr_name.startswith("test_"):
                method = getattr(instance, attr_name)
                if callable(method):
                    try:
                        method()
                        print(f"  [PASS] {cls.__name__}.{attr_name}")
                        passed += 1
                    except Exception as e:
                        print(f"  [FAIL] {cls.__name__}.{attr_name}: {e}")
                        failed += 1

    print(f"\nResult: {passed} passed, {failed} failed.")
    if failed > 0:
        exit(1)

