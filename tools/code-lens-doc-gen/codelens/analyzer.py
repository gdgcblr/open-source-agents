"""
Code Analyzer — Extracts structural information from source files.

Responsibilities:
- Python files: Full AST parsing (classes, functions, args, docstrings, decorators)
- Other languages: Regex-based heuristic extraction of functions and classes
- Config files: Key extraction from YAML/JSON/TOML/INI
- All languages: Identifies public vs private symbols

No LLM calls happen here — this is pure local static analysis.
"""

import ast
import re
from pathlib import Path


def analyze_file(file_info: dict) -> dict:
    """
    Analyze a single file and extract its structural components.

    Args:
        file_info: A dict from the scanner containing at minimum:
            - path: relative file path
            - language: detected language string
            - category: "source" | "config" | "doc" | "other"
            - content: file content string

    Returns:
        A dict with the analysis results:
        {
            "path": str,
            "language": str,
            "category": str,
            "module_docstring": str | None,
            "classes": [...],
            "functions": [...],
            "imports": [...],
            "exports": [...],
            "config_keys": [...],
            "summary_lines": int,
        }
    """
    language = file_info.get("language", "unknown")
    content = file_info.get("content", "")
    category = file_info.get("category", "other")

    base_result = {
        "path": file_info["path"],
        "language": language,
        "category": category,
        "module_docstring": None,
        "classes": [],
        "functions": [],
        "imports": [],
        "exports": [],
        "config_keys": [],
        "summary_lines": file_info.get("line_count", 0),
    }

    if not content.strip():
        return base_result

    if language == "python":
        return _analyze_python(content, base_result)
    elif language in ("javascript", "typescript"):
        return _analyze_js_ts(content, base_result)
    elif language == "go":
        return _analyze_go(content, base_result)
    elif language == "java":
        return _analyze_java(content, base_result)
    elif category == "config":
        return _analyze_config(content, base_result, language)
    else:
        return _analyze_generic(content, base_result)


def analyze_codebase(codebase_map: dict) -> list[dict]:
    """
    Analyze all files in a codebase map.

    Args:
        codebase_map: The output from scanner.scan_codebase()

    Returns:
        A list of analysis dicts, one per file.
    """
    results = []
    for file_info in codebase_map.get("files", []):
        analysis = analyze_file(file_info)
        results.append(analysis)
    return results


# =============================================================================
# Python Analyzer (AST-based — most thorough)
# =============================================================================

def _analyze_python(content: str, result: dict) -> dict:
    """Full AST-based analysis for Python files."""
    try:
        tree = ast.parse(content)
    except SyntaxError:
        # If AST parsing fails, fall back to generic analysis
        return _analyze_generic(content, result)

    result["module_docstring"] = ast.get_docstring(tree)

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef):
            result["classes"].append(_extract_python_class(node))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            result["functions"].append(_extract_python_function(node))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                result["imports"].append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                result["imports"].append(f"{module}.{alias.name}")

    return result


def _extract_python_class(node: ast.ClassDef) -> dict:
    """Extract class information from an AST ClassDef node."""
    methods = []
    for item in node.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            methods.append(_extract_python_function(item))

    return {
        "name": node.name,
        "docstring": ast.get_docstring(node),
        "methods": methods,
        "bases": [_get_ast_name(b) for b in node.bases],
        "decorators": [_get_ast_name(d) for d in node.decorator_list],
        "line": node.lineno,
        "is_private": node.name.startswith("_"),
    }


def _extract_python_function(node) -> dict:
    """Extract function information from an AST FunctionDef node."""
    args = []
    for arg in node.args.args:
        arg_name = arg.arg
        annotation = ""
        if arg.annotation:
            annotation = _get_ast_name(arg.annotation)
        args.append({"name": arg_name, "type": annotation})

    return_annotation = ""
    if node.returns:
        return_annotation = _get_ast_name(node.returns)

    return {
        "name": node.name,
        "docstring": ast.get_docstring(node),
        "args": args,
        "return_type": return_annotation,
        "decorators": [_get_ast_name(d) for d in node.decorator_list],
        "is_async": isinstance(node, ast.AsyncFunctionDef),
        "line": node.lineno,
        "is_private": node.name.startswith("_"),
    }


def _get_ast_name(node) -> str:
    """Safely extract a name string from various AST node types."""
    if isinstance(node, ast.Name):
        return node.id
    elif isinstance(node, ast.Attribute):
        return f"{_get_ast_name(node.value)}.{node.attr}"
    elif isinstance(node, ast.Call):
        return _get_ast_name(node.func)
    elif isinstance(node, ast.Constant):
        return str(node.value)
    elif isinstance(node, ast.Subscript):
        return f"{_get_ast_name(node.value)}[{_get_ast_name(node.slice)}]"
    elif isinstance(node, ast.Tuple):
        return ", ".join(_get_ast_name(e) for e in node.elts)
    else:
        return "<complex>"


# =============================================================================
# JavaScript / TypeScript Analyzer (regex-based)
# =============================================================================

def _analyze_js_ts(content: str, result: dict) -> dict:
    """Regex-based analysis for JavaScript/TypeScript files."""

    # Extract class definitions
    class_pattern = re.compile(
        r'(?:export\s+)?(?:default\s+)?class\s+(\w+)(?:\s+extends\s+([\w.]+))?',
        re.MULTILINE,
    )
    for match in class_pattern.finditer(content):
        result["classes"].append({
            "name": match.group(1),
            "docstring": None,
            "methods": [],
            "bases": [match.group(2)] if match.group(2) else [],
            "decorators": [],
            "line": content[:match.start()].count("\n") + 1,
            "is_private": match.group(1).startswith("_"),
        })

    # Extract function definitions (named functions and arrow functions)
    func_patterns = [
        # function declarations
        re.compile(
            r'(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)',
            re.MULTILINE,
        ),
        # const arrow functions
        re.compile(
            r'(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\([^)]*\)\s*=>',
            re.MULTILINE,
        ),
    ]

    for pattern in func_patterns:
        for match in func_patterns[0].finditer(content):
            result["functions"].append({
                "name": match.group(1),
                "docstring": None,
                "args": [],
                "return_type": "",
                "decorators": [],
                "is_async": "async" in match.group(0),
                "line": content[:match.start()].count("\n") + 1,
                "is_private": match.group(1).startswith("_"),
            })

    # Extract exports
    export_pattern = re.compile(r'export\s+(?:default\s+)?(?:const|let|var|function|class)\s+(\w+)', re.MULTILINE)
    for match in export_pattern.finditer(content):
        result["exports"].append(match.group(1))

    # Extract imports
    import_pattern = re.compile(r'import\s+.*?\s+from\s+["\']([^"\']+)["\']', re.MULTILINE)
    for match in import_pattern.finditer(content):
        result["imports"].append(match.group(1))

    return result


# =============================================================================
# Go Analyzer (regex-based)
# =============================================================================

def _analyze_go(content: str, result: dict) -> dict:
    """Regex-based analysis for Go files."""

    # Extract struct definitions (Go's equivalent of classes)
    struct_pattern = re.compile(r'type\s+(\w+)\s+struct\s*\{', re.MULTILINE)
    for match in struct_pattern.finditer(content):
        result["classes"].append({
            "name": match.group(1),
            "docstring": None,
            "methods": [],
            "bases": [],
            "decorators": [],
            "line": content[:match.start()].count("\n") + 1,
            "is_private": match.group(1)[0].islower(),  # Go: lowercase = unexported
        })

    # Extract function definitions
    func_pattern = re.compile(r'func\s+(?:\([^)]+\)\s+)?(\w+)\s*\(([^)]*)\)', re.MULTILINE)
    for match in func_pattern.finditer(content):
        result["functions"].append({
            "name": match.group(1),
            "docstring": None,
            "args": [],
            "return_type": "",
            "decorators": [],
            "is_async": False,
            "line": content[:match.start()].count("\n") + 1,
            "is_private": match.group(1)[0].islower(),
        })

    # Extract imports
    import_pattern = re.compile(r'"([^"]+)"', re.MULTILINE)
    import_block = re.search(r'import\s*\((.*?)\)', content, re.DOTALL)
    if import_block:
        for match in import_pattern.finditer(import_block.group(1)):
            result["imports"].append(match.group(1))

    return result


# =============================================================================
# Java Analyzer (regex-based)
# =============================================================================

def _analyze_java(content: str, result: dict) -> dict:
    """Regex-based analysis for Java files."""

    # Extract class definitions
    class_pattern = re.compile(
        r'(?:public|private|protected)?\s*(?:abstract\s+)?(?:final\s+)?class\s+(\w+)'
        r'(?:\s+extends\s+(\w+))?(?:\s+implements\s+([\w,\s]+))?',
        re.MULTILINE,
    )
    for match in class_pattern.finditer(content):
        result["classes"].append({
            "name": match.group(1),
            "docstring": None,
            "methods": [],
            "bases": [match.group(2)] if match.group(2) else [],
            "decorators": [],
            "line": content[:match.start()].count("\n") + 1,
            "is_private": False,
        })

    # Extract method definitions
    method_pattern = re.compile(
        r'(?:public|private|protected)\s+(?:static\s+)?(?:final\s+)?(\w+)\s+(\w+)\s*\(([^)]*)\)',
        re.MULTILINE,
    )
    for match in method_pattern.finditer(content):
        result["functions"].append({
            "name": match.group(2),
            "docstring": None,
            "args": [],
            "return_type": match.group(1),
            "decorators": [],
            "is_async": False,
            "line": content[:match.start()].count("\n") + 1,
            "is_private": False,
        })

    # Extract imports
    import_pattern = re.compile(r'import\s+([\w.]+);', re.MULTILINE)
    for match in import_pattern.finditer(content):
        result["imports"].append(match.group(1))

    return result


# =============================================================================
# Config File Analyzer
# =============================================================================

def _analyze_config(content: str, result: dict, language: str) -> dict:
    """Extract top-level keys from configuration files."""

    if language == "json":
        # Extract top-level keys from JSON
        key_pattern = re.compile(r'^\s*"(\w+)"\s*:', re.MULTILINE)
        for match in key_pattern.finditer(content):
            result["config_keys"].append(match.group(1))

    elif language in ("yaml", "toml", "ini"):
        # Extract top-level keys (lines starting without whitespace, before a colon or equals)
        key_pattern = re.compile(r'^([a-zA-Z_][\w.-]*)\s*[:=]', re.MULTILINE)
        for match in key_pattern.finditer(content):
            result["config_keys"].append(match.group(1))

    return result


# =============================================================================
# Generic Analyzer (fallback)
# =============================================================================

def _analyze_generic(content: str, result: dict) -> dict:
    """
    Fallback analyzer for languages without specific support.
    Extracts basic patterns like function-like definitions.
    """
    # Generic function-like pattern: word followed by parentheses
    func_pattern = re.compile(
        r'(?:def|func|function|fn|sub|proc)\s+(\w+)\s*\(', re.MULTILINE
    )
    for match in func_pattern.finditer(content):
        result["functions"].append({
            "name": match.group(1),
            "docstring": None,
            "args": [],
            "return_type": "",
            "decorators": [],
            "is_async": False,
            "line": content[:match.start()].count("\n") + 1,
            "is_private": match.group(1).startswith("_"),
        })

    return result


def condense_for_llm(analyses: list[dict], max_content_chars: int = 50000) -> str:
    """
    Create a condensed text summary of the codebase analysis
    suitable for sending to an LLM for categorization and doc generation.

    This strips out raw file content and focuses on structure:
    file paths, classes, functions, signatures, docstrings, imports.

    Args:
        analyses: List of analysis dicts from analyze_codebase().
        max_content_chars: Maximum total characters for the output.

    Returns:
        A formatted string summarizing the codebase structure.
    """
    lines = []
    total_chars = 0

    for analysis in analyses:
        section = []
        section.append(f"\n## File: {analysis['path']} ({analysis['language']})")

        if analysis.get("module_docstring"):
            doc = analysis["module_docstring"][:200]
            section.append(f"  Module docstring: {doc}")

        for cls in analysis.get("classes", []):
            visibility = "private" if cls.get("is_private") else "public"
            bases = f" extends {', '.join(cls['bases'])}" if cls.get("bases") else ""
            section.append(f"  Class: {cls['name']} ({visibility}){bases}")
            if cls.get("docstring"):
                section.append(f"    Docstring: {cls['docstring'][:150]}")
            for method in cls.get("methods", []):
                m_vis = "private" if method.get("is_private") else "public"
                async_tag = "async " if method.get("is_async") else ""
                args_str = ", ".join(
                    a["name"] + (f": {a['type']}" if a.get("type") else "")
                    for a in method.get("args", [])
                )
                ret = f" -> {method['return_type']}" if method.get("return_type") else ""
                section.append(f"    Method: {async_tag}{method['name']}({args_str}){ret} ({m_vis})")
                if method.get("docstring"):
                    section.append(f"      Docstring: {method['docstring'][:100]}")

        for func in analysis.get("functions", []):
            visibility = "private" if func.get("is_private") else "public"
            async_tag = "async " if func.get("is_async") else ""
            args_str = ", ".join(
                a["name"] + (f": {a['type']}" if a.get("type") else "")
                for a in func.get("args", [])
            )
            ret = f" -> {func['return_type']}" if func.get("return_type") else ""
            section.append(f"  Function: {async_tag}{func['name']}({args_str}){ret} ({visibility})")
            if func.get("docstring"):
                section.append(f"    Docstring: {func['docstring'][:100]}")

        if analysis.get("imports"):
            section.append(f"  Imports: {', '.join(analysis['imports'][:15])}")

        if analysis.get("exports"):
            section.append(f"  Exports: {', '.join(analysis['exports'][:15])}")

        if analysis.get("config_keys"):
            section.append(f"  Config keys: {', '.join(analysis['config_keys'][:20])}")

        section_text = "\n".join(section)

        if total_chars + len(section_text) > max_content_chars:
            lines.append(f"\n... (truncated — {len(analyses) - len(lines)} more files)")
            break

        lines.append(section_text)
        total_chars += len(section_text)

    return "\n".join(lines)
