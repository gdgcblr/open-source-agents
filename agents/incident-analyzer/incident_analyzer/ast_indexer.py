"""AST indexer for the Incident Analyzer.

Walks a Python codebase, parses every .py file using Python's ast module,
and generates a structured JSON specification (CodebaseSpec) for use during
incident diagnosis. This is the one-time setup step.
"""

from __future__ import annotations

import ast
import logging
import os

from .models import CodeSymbol, CodebaseSpec, ModuleSpec, SymbolType

logger = logging.getLogger(__name__)

# Directories to exclude from indexing by default
DEFAULT_EXCLUDE_DIRS = [
    ".venv", "venv", "node_modules", "__pycache__", ".git",
    ".tox", "dist", "build", ".eggs", ".mypy_cache", ".pytest_cache",
]


def _reconstruct_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """Reconstruct function signature from AST node."""
    args = node.args
    parts = []

    # Positional args
    num_defaults = len(args.defaults)
    num_args = len(args.args)
    for i, arg in enumerate(args.args):
        annotation = ""
        if arg.annotation:
            try:
                annotation = f": {ast.unparse(arg.annotation)}"
            except Exception:
                annotation = ": ..."
        default_index = i - (num_args - num_defaults)
        if default_index >= 0:
            try:
                default_val = f"={ast.unparse(args.defaults[default_index])}"
            except Exception:
                default_val = "=..."
            parts.append(f"{arg.arg}{annotation}{default_val}")
        else:
            parts.append(f"{arg.arg}{annotation}")

    # *args
    if args.vararg:
        parts.append(f"*{args.vararg.arg}")

    # keyword-only args
    for i, arg in enumerate(args.kwonlyargs):
        annotation = ""
        if arg.annotation:
            try:
                annotation = f": {ast.unparse(arg.annotation)}"
            except Exception:
                annotation = ": ..."
        if i < len(args.kw_defaults) and args.kw_defaults[i] is not None:
            try:
                default_val = f"={ast.unparse(args.kw_defaults[i])}"
            except Exception:
                default_val = "=..."
            parts.append(f"{arg.arg}{annotation}{default_val}")
        else:
            parts.append(f"{arg.arg}{annotation}")

    # **kwargs
    if args.kwarg:
        parts.append(f"**{args.kwarg.arg}")

    # Return annotation
    return_annotation = ""
    if node.returns:
        try:
            return_annotation = f" -> {ast.unparse(node.returns)}"
        except Exception:
            return_annotation = " -> ..."

    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    return f"{prefix} {node.name}({', '.join(parts)}){return_annotation}"


def _extract_calls(node: ast.AST) -> list[str]:
    """Extract names of functions/methods called within an AST node."""
    calls = []
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            if isinstance(child.func, ast.Name):
                calls.append(child.func.id)
            elif isinstance(child.func, ast.Attribute):
                calls.append(child.func.attr)
    return list(set(calls))


def _extract_decorators(
    node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
) -> list[str]:
    """Extract decorator names from an AST node."""
    decorators = []
    for dec in node.decorator_list:
        if isinstance(dec, ast.Name):
            decorators.append(dec.id)
        elif isinstance(dec, ast.Attribute):
            try:
                decorators.append(ast.unparse(dec))
            except Exception:
                decorators.append(dec.attr)
        elif isinstance(dec, ast.Call):
            if isinstance(dec.func, ast.Name):
                decorators.append(dec.func.id)
            elif isinstance(dec.func, ast.Attribute):
                try:
                    decorators.append(ast.unparse(dec.func))
                except Exception:
                    decorators.append(dec.func.attr)
    return decorators


def _get_source_snippet(source_lines: list[str], start: int, max_lines: int = 10) -> str:
    """Extract a source snippet starting from a 1-indexed line number."""
    start_idx = max(0, start - 1)
    end_idx = min(len(source_lines), start_idx + max_lines)
    return "\n".join(source_lines[start_idx:end_idx])


def _get_end_line(node: ast.AST) -> int:
    """Get the end line number of an AST node."""
    if hasattr(node, "end_lineno") and node.end_lineno is not None:
        return node.end_lineno
    # Fallback: estimate from body
    max_line = getattr(node, "lineno", 0)
    for child in ast.walk(node):
        child_line = getattr(child, "end_lineno", None) or getattr(child, "lineno", 0)
        if child_line > max_line:
            max_line = child_line
    return max_line


def index_file(file_path: str, root_path: str) -> ModuleSpec:
    """Parse a single Python file and extract its AST specification.

    Args:
        file_path: Absolute path to the Python file.
        root_path: Root path of the codebase for relative path calculation.

    Returns:
        ModuleSpec containing the file's symbols, imports, and docstring.
    """
    rel_path = os.path.relpath(file_path, root_path)

    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            source = f.read()
    except (OSError, IOError) as e:
        logger.warning("Could not read %s: %s", file_path, e)
        return ModuleSpec(file_path=rel_path)

    try:
        tree = ast.parse(source, filename=file_path)
    except SyntaxError as e:
        logger.warning("Syntax error in %s: %s", file_path, e)
        return ModuleSpec(file_path=rel_path)

    source_lines = source.splitlines()
    module_docstring = ast.get_docstring(tree)
    imports: list[str] = []
    symbols: list[CodeSymbol] = []

    for node in ast.iter_child_nodes(tree):
        # Extract imports
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module_name = node.module or ""
            for alias in node.names:
                imports.append(f"from {module_name} import {alias.name}")

        # Extract top-level functions
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            end_line = _get_end_line(node)
            symbols.append(CodeSymbol(
                name=node.name,
                symbol_type=SymbolType.FUNCTION,
                file_path=rel_path,
                line_start=node.lineno,
                line_end=end_line,
                signature=_reconstruct_signature(node),
                docstring=ast.get_docstring(node),
                decorators=_extract_decorators(node),
                calls=_extract_calls(node),
                source_snippet=_get_source_snippet(source_lines, node.lineno),
            ))

        # Extract classes and their methods
        elif isinstance(node, ast.ClassDef):
            class_end = _get_end_line(node)
            class_symbol = CodeSymbol(
                name=node.name,
                symbol_type=SymbolType.CLASS,
                file_path=rel_path,
                line_start=node.lineno,
                line_end=class_end,
                signature=f"class {node.name}",
                docstring=ast.get_docstring(node),
                decorators=_extract_decorators(node),
                calls=_extract_calls(node),
                source_snippet=_get_source_snippet(source_lines, node.lineno),
            )
            symbols.append(class_symbol)

            # Extract methods
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    method_end = _get_end_line(item)
                    symbols.append(CodeSymbol(
                        name=item.name,
                        symbol_type=SymbolType.METHOD,
                        file_path=rel_path,
                        line_start=item.lineno,
                        line_end=method_end,
                        signature=_reconstruct_signature(item),
                        docstring=ast.get_docstring(item),
                        decorators=_extract_decorators(item),
                        calls=_extract_calls(item),
                        source_snippet=_get_source_snippet(source_lines, item.lineno),
                    ))

    return ModuleSpec(
        file_path=rel_path,
        imports=imports,
        symbols=symbols,
        module_docstring=module_docstring,
    )


def index_codebase(
    root_path: str, exclude_dirs: list[str] | None = None
) -> CodebaseSpec:
    """Walk a codebase directory and index all Python files.

    Args:
        root_path: Absolute path to the root of the codebase.
        exclude_dirs: Directory names to skip. Uses DEFAULT_EXCLUDE_DIRS if None.

    Returns:
        CodebaseSpec containing all indexed modules and symbols.
    """
    if exclude_dirs is None:
        exclude_dirs = DEFAULT_EXCLUDE_DIRS

    root_path = os.path.abspath(root_path)
    modules: list[ModuleSpec] = []
    total_symbols = 0

    for dirpath, dirnames, filenames in os.walk(root_path):
        # Filter out excluded directories in-place to prevent os.walk from descending
        dirnames[:] = [d for d in dirnames if d not in exclude_dirs]

        for filename in filenames:
            if not filename.endswith(".py"):
                continue
            file_path = os.path.join(dirpath, filename)
            module_spec = index_file(file_path, root_path)
            modules.append(module_spec)
            total_symbols += len(module_spec.symbols)

    spec = CodebaseSpec(
        root_path=root_path,
        modules=modules,
        total_symbols=total_symbols,
        total_files=len(modules),
    )

    logger.info(
        "Indexed %d files with %d symbols from %s",
        spec.total_files, spec.total_symbols, root_path,
    )
    return spec


def save_spec(spec: CodebaseSpec, output_path: str) -> None:
    """Save a CodebaseSpec to a JSON file.

    Args:
        spec: The codebase specification to save.
        output_path: Path to write the JSON file.
    """
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(spec.model_dump_json(indent=2))
    logger.info("Saved codebase spec to %s", output_path)


def load_spec(spec_path: str) -> CodebaseSpec:
    """Load a CodebaseSpec from a JSON file.

    Args:
        spec_path: Path to the JSON spec file.

    Returns:
        The loaded CodebaseSpec.

    Raises:
        FileNotFoundError: If the spec file does not exist.
    """
    with open(spec_path, "r", encoding="utf-8") as f:
        content = f.read()
    spec = CodebaseSpec.model_validate_json(content)
    logger.info(
        "Loaded codebase spec: %d files, %d symbols",
        spec.total_files, spec.total_symbols,
    )
    return spec


def generate_spec_markdown(spec: CodebaseSpec) -> str:
    """Generate a clean, human-readable Markdown specification of the codebase.

    Args:
        spec: The codebase specification.

    Returns:
        Markdown-formatted string representing the codebase architecture and symbols.
    """
    lines = [
        f"# Codebase Specification: `{os.path.basename(spec.root_path)}`",
        "",
        f"- **Root Path**: `{spec.root_path}`",
        f"- **Total Files**: {spec.total_files}",
        f"- **Total Symbols**: {spec.total_symbols}",
        "",
        "---",
        "",
        "## Modules & Symbols",
        "",
    ]
    for module in spec.modules:
        lines.append(f"### Module `{module.file_path}`")
        if module.module_docstring:
            lines.append(f"> {module.module_docstring.strip()}")
            lines.append("")
        if module.imports:
            lines.append("**Imports:**")
            for imp in module.imports:
                lines.append(f"- `{imp}`")
            lines.append("")
        if module.symbols:
            lines.append("**Symbols:**")
            for sym in module.symbols:
                lines.append(f"- **`{sym.name}`** ({sym.symbol_type.value}, lines {sym.line_start}-{sym.line_end})")
                lines.append(f"  - Signature: `{sym.signature}`")
                if sym.docstring:
                    lines.append(f"  - Description: {sym.docstring.strip().splitlines()[0]}")
                if sym.calls:
                    lines.append(f"  - Calls: {', '.join(f'`{c}`' for c in sym.calls)}")
            lines.append("")
        else:
            lines.append("*No top-level functions or classes defined.*")
            lines.append("")
    return "\n".join(lines)


def save_spec_markdown(spec: CodebaseSpec, output_path: str) -> None:
    """Save a human-readable Markdown specification to a file.

    Args:
        spec: The codebase specification.
        output_path: Path to write the Markdown file.
    """
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(generate_spec_markdown(spec))
    logger.info("Saved codebase markdown spec to %s", output_path)

