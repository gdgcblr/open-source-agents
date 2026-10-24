"""Facts read from source code by plain code, without the model.

outline() shrinks a source file to its declarations and their first doc line,
find_settings() lists the environment variables the code reads, and
import_diagram() draws which parts of the project import which as a Mermaid graph.
All three take text that tools.py has already redacted, and none of them runs code.
"""

from __future__ import annotations

import ast
import posixpath
import re
import sys
from collections import Counter, defaultdict

from .guardrails import is_secret_name, redact

OUTLINE_MAX_LINES = 60
OUTLINE_LINE_CHARS = 160
MAX_SETTINGS = 60
DIAGRAM_MAX_NODES = 14
DIAGRAM_MAX_EDGES = 24

_FAMILIES = {
    ".py": "python", ".js": "js", ".jsx": "js", ".mjs": "js", ".cjs": "js", ".ts": "js", ".tsx": "js",
    ".go": "go", ".rs": "rust", ".rb": "ruby", ".php": "php", ".sh": "shell",
    ".java": "jvm", ".kt": "jvm", ".cs": "jvm", ".swift": "jvm", ".dart": "jvm",
    ".c": "c", ".cpp": "c", ".h": "c", ".hpp": "c",
}
# Lines that declare something worth listing, per language family. Used for every language
# except Python, which is parsed with ast (and falls back to these on a syntax error).
_DECLARATION_RES = {
    family: [re.compile(pattern) for pattern in patterns]
    for family, patterns in {
        "python": [r"^\s*(?:async\s+)?def\s+[A-Za-z]\w*\s*\(", r"^\s*class\s+[A-Za-z]\w*"],
        "js": [
            r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\b",
            r"^\s*(?:export\s+)?(?:default\s+)?(?:abstract\s+)?class\s+[\w$]+",
            r"^\s*export\s+(?:const|let)\s+[\w$]+\s*=\s*(?:async\s*)?(?:\([^)]*\)|[\w$]+)\s*=>",
            r"^\s*(?:export\s+)?(?:declare\s+)?(?:interface|type|enum)\s+[\w$]+",
        ],
        "go": [r"^func\s", r"^type\s+\w+\s+(?:struct|interface)\b"],
        "rust": [
            r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:async\s+|const\s+|unsafe\s+)*fn\s+\w+",
            r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:struct|enum|trait|mod)\s+\w+",
            r"^\s*impl\b",
        ],
        "jvm": [  # Java, Kotlin, C#, Swift, Dart
            r"^\s*(?:[\w@]+\s+)*(?:class|interface|enum|record|struct|object|protocol|extension|mixin)\s+\w+",
            r"^\s*(?:public|protected|internal|open|override)\s+[\w<>\[\],.?\s]*\w+\s*\(",
            r"^\s*(?:\w+\s+)*(?:fun|func)\s+[\w.<>]+\s*\(",
        ],
        "ruby": [r"^\s*(?:class|module)\s+[\w:]+", r"^\s*def\s+[\w.?!=]+"],
        "php": [
            r"^\s*(?:abstract\s+|final\s+|readonly\s+)*(?:class|interface|trait|enum)\s+\w+",
            r"^\s*(?:public\s+|protected\s+|static\s+|final\s+|abstract\s+)*function\s+\w+",
        ],
        "c": [
            r"^\s*(?:class|struct|namespace|enum)\s+\w+[^;]*$",
            r"^(?!(?:if|for|while|switch|return|else|do|case|typedef)\b)[A-Za-z_][\w\s*&:<>,]*?\b\w+\s*\([^;]*\)\s*(?:const\s*)?\{?\s*$",
        ],
        "shell": [r"^\s*(?:function\s+)?[\w-]+\s*\(\)\s*\{?\s*$", r"^\s*function\s+[\w-]+"],
    }.items()
}
_LICENSE_RE = re.compile(r"(?i)copyright|licen[cs]e|spdx|all rights reserved")
# Command-line options and web routes: the lines a README's "How to Run" needs.
_NOTABLE_RE = re.compile(
    r"\.add_argument\(\s*['\"]"
    r"|\b(?:app|router|server|api|bp)\.(?:get|post|put|patch|delete|route)\(\s*['\"`]/"
)

_ENV_NAME = r"(?P<name>[A-Za-z_][A-Za-z0-9_]*)"
_ENV_DEFAULT = r"""(?P<default>"[^"\n]*"|'[^'\n]*'|`[^`\n]*`|-?\d+(?:\.\d+)?\b|True|False|true|false)"""
_SETTING_RES = [  # (pattern, the program fails without the variable when no default is given)
    (re.compile(pattern), fails_without)
    for pattern, fails_without in [
        (rf"""\bos\.(?:getenv|environ\.get)\(\s*["']{_ENV_NAME}["']\s*(?:,\s*(?:default\s*=\s*)?{_ENV_DEFAULT})?""", False),
        (rf"""\bos\.(?:getenv|environ\.get)\(\s*["']{_ENV_NAME}["']\s*\)\s*or\s+{_ENV_DEFAULT}""", False),
        (rf"""\bos\.environ\.setdefault\(\s*["']{_ENV_NAME}["']\s*,\s*{_ENV_DEFAULT}""", False),
        (rf"""\bos\.environ\[\s*["']{_ENV_NAME}["']\s*\]""", True),
        (rf"""\bprocess\.env\.{_ENV_NAME}(?:\s*(?:\|\||\?\?)\s*{_ENV_DEFAULT})?""", False),
        (rf"""\bprocess\.env\[\s*["'`]{_ENV_NAME}["'`]\s*\](?:\s*(?:\|\||\?\?)\s*{_ENV_DEFAULT})?""", False),
        (rf"""\bimport\.meta\.env\.{_ENV_NAME}""", False),
        (rf"""\bDeno\.env\.get\(\s*["']{_ENV_NAME}["']""", False),
        (rf"""\bos\.(?:Getenv|LookupEnv)\(\s*"{_ENV_NAME}"\s*\)""", False),
        (rf"""\benv::var(?:_os)?\(\s*"{_ENV_NAME}"\s*\)(?:\s*\.unwrap_or\(\s*{_ENV_DEFAULT})?""", False),
        (rf"""\bSystem\.getenv\(\s*"{_ENV_NAME}"\s*\)""", False),
        (rf"""\bEnvironment\.GetEnvironmentVariable\(\s*"{_ENV_NAME}"\s*\)""", False),
        (rf"""\bENV\.fetch\(\s*["']{_ENV_NAME}["']\s*(?:,\s*{_ENV_DEFAULT})?""", True),
        (rf"""\bENV\[\s*["']{_ENV_NAME}["']\s*\](?:\s*\|\|\s*{_ENV_DEFAULT})?""", False),
        (rf"""\bgetenv\(\s*["']{_ENV_NAME}["']\s*\)""", False),
        (rf"""\$_(?:ENV|SERVER)\[\s*["']{_ENV_NAME}["']\s*\]""", False),
        (rf"""(?<![\w.])env\(\s*["']{_ENV_NAME}["']\s*(?:,\s*{_ENV_DEFAULT})?""", False),
        (rf"""\bPlatform\.environment\[\s*["']{_ENV_NAME}["']\s*\]""", False),
        (rf"""\bString\.fromEnvironment\(\s*["']{_ENV_NAME}["']\s*(?:,\s*defaultValue:\s*{_ENV_DEFAULT})?""", False),
        (rf"""\.environment\[\s*"{_ENV_NAME}"\s*\]""", False),
    ]
]
# ${NAME}, ${NAME:-default} and ${NAME:?error} in shell scripts and Compose files.
_SHELL_SETTING_RE = re.compile(r"\$\{(?P<name>[A-Za-z_][A-Za-z0-9_]*)(?:(?P<op>:?[-?=+])(?P<value>[^}]*))?\}")
_SYSTEM_VARIABLES = {
    "HOME", "PATH", "PWD", "OLDPWD", "USER", "USERNAME", "SHELL", "TERM", "TMPDIR", "TMP", "TEMP",
    "LANG", "LC_ALL", "HOSTNAME",
}
_COMPOSE_NAMES = ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml")

_JS_IMPORT_RE = re.compile(r"""(?:\bfrom|\bimport|\brequire)\s*\(?\s*['"]([^'"\n]+)['"]""")
_JS_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".vue", ".svelte")
_GO_IMPORT_RE = re.compile(r'^\s*import\s*(?:\((?P<block>[^)]*)\)|(?:[\w.]+\s+)?"(?P<one>[^"]+)")', re.M)
_RUST_MOD_RE = re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?mod\s+(\w+)\s*;", re.M)
_RUST_USE_RE = re.compile(r"\buse\s+crate::((?:\w+::)*\w+)")
_C_INCLUDE_RE = re.compile(r'^\s*#\s*include\s*"([^"]+)"', re.M)
_RUBY_REQUIRE_RE = re.compile(r"""\brequire_relative\s*\(?\s*['"]([^'"]+)['"]""")


def is_test_file(path: str) -> bool:
    """True for test code, which the settings scan, the diagram and big-project mode leave out."""
    parts = path.split("/")
    name = parts[-1]
    return (
        any(part in ("test", "tests", "__tests__", "spec", "specs", "testdata") for part in parts[:-1])
        or name.startswith(("test_", "test.")) or name == "conftest.py"
        or re.search(r"(?:_test|_spec|\.test|\.spec)\.\w+$", name) is not None
    )


def outline(path: str, text: str) -> str:
    """Returns a compact outline of one source file.

    The outline keeps the file's header doc line, the classes and functions it declares
    with their first doc line, its command-line options and its web routes. Function
    bodies are left out, so an outline is usually about 5% of the file.
    """
    suffix = posixpath.splitext(path)[1]
    lines = _python_outline(text) if suffix == ".py" else None
    if lines is None:
        lines = _regex_outline(_FAMILIES.get(suffix, ""), text)
    lines += _notable_lines(text, set(lines), skip_decorators=suffix == ".py")
    if len(lines) > OUTLINE_MAX_LINES:
        lines = lines[:OUTLINE_MAX_LINES] + [f"... and {len(lines) - OUTLINE_MAX_LINES} more lines"]
    return "\n".join([f"== {path} =="] + [line[:OUTLINE_LINE_CHARS] for line in lines]) + "\n"


def _short(text: str) -> str:
    first = next((line.strip() for line in text.splitlines() if line.strip()), "")
    return first.split(". ")[0][:100]


def _python_outline(text: str) -> list[str] | None:
    try:
        tree = ast.parse(text)
        doc = ast.get_docstring(tree)
        lines = [f'"""{_short(doc)}"""'] if doc else []
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
                lines += _python_function(node, "")
            elif isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
                bases = ", ".join(ast.unparse(base) for base in node.bases)
                lines.append((f"class {node.name}({bases})" if bases else f"class {node.name}") + _python_doc(node))
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and not item.name.startswith("_"):
                        lines += _python_function(item, "    ")
            elif isinstance(node, ast.If) and "__main__" in ast.unparse(node.test):
                lines.append('if __name__ == "__main__": runs as a script')
        return lines
    except (SyntaxError, ValueError, RecursionError):
        return None


def _python_function(node: ast.FunctionDef | ast.AsyncFunctionDef, indent: str) -> list[str]:
    # Only decorators that are calls: @app.get("/users") and @click.option(...) say something,
    # @property and @staticmethod do not.
    lines = [f"{indent}@{ast.unparse(d)}" for d in node.decorator_list if isinstance(d, ast.Call)]
    kind = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    returns = f" -> {ast.unparse(node.returns)}" if node.returns else ""
    lines.append(f"{indent}{kind} {node.name}({ast.unparse(node.args)}){returns}{_python_doc(node)}")
    return lines


def _python_doc(node: ast.AST) -> str:
    doc = ast.get_docstring(node)
    return f"  # {_short(doc)}" if doc else ""


def _comment(line: str, family: str) -> str | None:
    """Returns the text of a comment line ('' if it has none), or None for a line of code."""
    stripped = line.strip()
    for marker in ("///", "//!", "//", "/**", "/*", "*/", "*"):
        if stripped.startswith(marker):
            return stripped[len(marker):].replace("*/", "").strip()
    if stripped.startswith("#") and family in ("python", "ruby", "shell") and not stripped.startswith("#!"):
        return stripped[1:].strip()
    return None


def _regex_outline(family: str, text: str) -> list[str]:
    patterns = _DECLARATION_RES.get(family, [])
    header, doc, doc_line, lines = None, None, -2, []
    for number, line in enumerate(text.splitlines()):
        if len(line) > 500:  # minified or generated code
            continue
        comment = _comment(line, family)
        if comment is not None:
            if doc_line != number - 1:
                doc = None  # a new comment block starts; keep its first line of text
            if doc is None and comment and not comment.startswith("@"):
                doc = comment
            if header is None and number < 15 and len(comment.split()) >= 3 and not _LICENSE_RE.search(comment):
                header = comment
            doc_line = number
            continue
        if any(pattern.search(line) for pattern in patterns):
            note = f"  // {_short(doc)}" if doc and doc_line == number - 1 else ""
            lines.append(line.strip().rstrip("{").rstrip() + note)
        if line.strip():
            doc = None
    return ([f"// {_short(header)}"] if header else []) + lines


def _notable_lines(text: str, already: set[str], skip_decorators: bool) -> list[str]:
    found = []
    for line in text.splitlines():
        stripped = line.strip()
        if skip_decorators and stripped.startswith("@"):
            continue  # Python decorators are already in the outline
        if len(stripped) <= 300 and _NOTABLE_RE.search(stripped) and stripped not in already and stripped not in found:
            found.append(stripped)
            if len(found) == 15:
                break
    return found


def find_settings(files: list[tuple[str, str]]) -> list[dict]:
    """Lists the environment variables the code reads, with the default written next to the read.

    Recognises os.getenv/os.environ (Python), process.env (JavaScript/TypeScript), os.Getenv
    (Go), env::var (Rust), System.getenv (Java/Kotlin), Environment.GetEnvironmentVariable (C#),
    ENV (Ruby), getenv/$_ENV/env() (PHP, C), Platform.environment (Dart) and ${NAME:-default}
    in shell scripts and Compose files. Test files are skipped.
    """
    found: dict[str, dict] = {}
    for path, text in files:
        if is_test_file(path):
            continue
        shell_like = path.endswith(".sh") or posixpath.basename(path) in _COMPOSE_NAMES
        if not (("${" in text) if shell_like else ("env" in text or "Env" in text or "ENV" in text)):
            continue  # every pattern needs one of these, and most files have none
        for name, default, required in (_shell_reads(text) if shell_like else _code_reads(text)):
            if name in _SYSTEM_VARIABLES:
                continue
            entry = found.setdefault(name, {"name": name, "default": None, "required": False, "read_in": []})
            if default is not None and entry["default"] is None:
                entry["default"] = _clean_default(name, default)
            entry["required"] = entry["required"] or required
            if path not in entry["read_in"] and len(entry["read_in"]) < 3:
                entry["read_in"].append(path)
    for entry in found.values():
        if entry["default"] is not None:
            entry["required"] = False
    return [found[name] for name in sorted(found)][:MAX_SETTINGS]


def _code_reads(text: str):
    for pattern, fails_without in _SETTING_RES:
        for match in pattern.finditer(text):
            default = match.groupdict().get("default")
            yield match.group("name"), default, fails_without and default is None


def _shell_reads(text: str):
    for match in _SHELL_SETTING_RE.finditer(text):
        op = match.group("op") or ""
        if "?" in op:
            yield match.group("name"), None, True
        elif op.lstrip(":") in ("-", "="):
            yield match.group("name"), match.group("value") or "", False
        else:
            yield match.group("name"), None, False


def _clean_default(name: str, raw: str) -> str:
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'`":
        value = value[1:-1]
    if value and is_secret_name(name) and not re.fullmatch(r"-?\d+(?:\.\d+)?|true|false", value, re.I):
        return "[REDACTED]"
    return redact(value)[:80]


def import_diagram(files: list[tuple[str, str]], all_paths: list[str], go_module: str | None = None) -> str | None:
    """Draws which parts of the project import which, as Mermaid source that GitHub shows as a picture.

    Follows imports between the project's own files in Python, JavaScript/TypeScript, Go, Rust,
    C/C++ (#include "...") and Ruby (require_relative). Small projects get one box per file,
    bigger ones one box per folder. Returns None when the project has no internal imports.
    """
    known = set(all_paths)
    python_modules, python_packages = _python_modules(all_paths)
    go_packages: dict[str, str] = {}
    by_name: dict[str, list[str]] = defaultdict(list)
    for path in sorted(all_paths):
        if path.endswith(".go") and not path.endswith("_test.go"):
            go_packages.setdefault(posixpath.dirname(path), path)
        by_name[posixpath.basename(path)].append(path)

    edges: Counter = Counter()
    for path, text in files:
        if is_test_file(path):
            continue
        suffix = posixpath.splitext(path)[1]
        family = _FAMILIES.get(suffix)
        if family == "python":
            targets = _python_imports(path, text, known, python_modules, python_packages)
        elif family == "js":
            targets = _js_imports(path, text, known)
        elif family == "go":
            targets = _go_imports(text, go_packages, go_module)
        elif family == "rust":
            targets = _rust_imports(path, text, known)
        elif family == "c":
            targets = _c_imports(path, text, known, by_name)
        elif family == "ruby":
            targets = _ruby_imports(path, text, known)
        else:
            continue
        for target in targets:
            if target and target != path and target in known and not is_test_file(target):
                edges[(path, target)] += 1
    return _mermaid(edges)


def _first(candidates: list[str], known: set[str]) -> str | None:
    return next((candidate for candidate in candidates if candidate in known), None)


def _python_modules(paths: list[str]) -> tuple[dict[str, list[str]], set[str]]:
    """Maps importable module names to files, following __init__.py packages up to their root.

    Also returns the package folders (those with an __init__.py).
    """
    packages = {posixpath.dirname(p) for p in paths if posixpath.basename(p) == "__init__.py"}
    modules = defaultdict(list)
    for path in paths:
        if not path.endswith(".py"):
            continue
        folder, name = posixpath.split(path[:-3])
        parts = [] if name == "__init__" else [name]
        while folder and folder in packages:  # stops at the project root, even when it is a package itself
            folder, package = posixpath.split(folder)
            parts.insert(0, package)
        if parts:
            modules[".".join(parts)].append(path)
    return modules, packages


def _python_module_file(name: str, importer: str, modules: dict[str, list[str]], packages: set[str]) -> str | None:
    parts = name.split(".")
    if parts[0] in sys.stdlib_module_names:
        return None
    for end in range(len(parts), 0, -1):
        candidates = modules.get(".".join(parts[:end]), [])
        if len(candidates) > 1:  # loose scripts with the same name: only a sibling can be meant
            candidates = [c for c in candidates if posixpath.dirname(c) == posixpath.dirname(importer)]
        if len(candidates) == 1:
            folder = posixpath.dirname(candidates[0])
            loose = folder not in packages and folder != "" and not candidates[0].endswith("__init__.py")
            if loose and folder != posixpath.dirname(importer):
                return None
            return candidates[0]
    return None


def _python_imports(
    path: str, text: str, known: set[str], modules: dict[str, list[str]], packages: set[str]
) -> list[str]:
    try:
        nodes = list(ast.walk(ast.parse(text)))
    except (SyntaxError, ValueError, RecursionError):
        return []
    targets = []
    for node in nodes:
        if isinstance(node, ast.Import):
            targets += [_python_module_file(alias.name, path, modules, packages) for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level:  # from . import x, from ..pkg import y
            base = posixpath.dirname(path)
            for _ in range(node.level - 1):
                base = posixpath.dirname(base)
            stem = posixpath.join(base, *node.module.split(".")) if node.module else base
            module = _first([stem + ".py", stem + "/__init__.py"], known) if node.module else None
            package = _first([posixpath.join(stem, "__init__.py")], known)
            for alias in node.names:  # an imported name can itself be a module: from . import tools
                sub = posixpath.join(stem, alias.name)
                targets.append(_first([sub + ".py", sub + "/__init__.py"], known) or module or package)
        elif isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:  # from a.b import c: c is a module or a name inside a.b
                targets.append(
                    _python_module_file(f"{node.module}.{alias.name}", path, modules, packages)
                    or _python_module_file(node.module, path, modules, packages)
                )
    return [t for t in targets if t]


def _js_imports(path: str, text: str, known: set[str]) -> list[str]:
    targets = []
    for spec in _JS_IMPORT_RE.findall(text):
        if not spec.startswith("."):
            continue  # a package from npm, not a project file
        base = posixpath.normpath(posixpath.join(posixpath.dirname(path), spec))
        if base.startswith(".."):
            continue
        stem, ext = posixpath.splitext(base)
        candidates = [base] + [base + e for e in _JS_EXTENSIONS] + [f"{base}/index{e}" for e in _JS_EXTENSIONS]
        if ext in (".js", ".jsx", ".mjs", ".cjs"):  # TypeScript imports ./x.js to mean ./x.ts
            candidates += [stem + e for e in (".ts", ".tsx", ".mts", ".cts")]
        target = _first(candidates, known)
        if target and posixpath.splitext(target)[1] in _JS_EXTENSIONS:
            targets.append(target)
    return targets


def _go_imports(text: str, go_packages: dict[str, str], module: str | None) -> list[str]:
    if not module:
        return []
    targets = []
    for match in _GO_IMPORT_RE.finditer(text):
        specs = re.findall(r'"([^"]+)"', match.group("block")) if match.group("block") else [match.group("one")]
        for spec in specs:
            if spec == module or spec.startswith(module + "/"):
                targets.append(go_packages.get(spec[len(module):].lstrip("/")))
    return [t for t in targets if t]


def _rust_imports(path: str, text: str, known: set[str]) -> list[str]:
    folder, name = posixpath.split(path[:-3])
    base = folder if name in ("main", "lib", "mod") else posixpath.join(folder, name)
    targets = [
        _first([posixpath.join(base, module + ".rs"), posixpath.join(base, module, "mod.rs")], known)
        for module in _RUST_MOD_RE.findall(text)
    ]
    parts = path.split("/")
    crate_root = "/".join(parts[: len(parts) - parts[::-1].index("src")]) if "src" in parts[:-1] else folder
    for use in _RUST_USE_RE.findall(text):
        names = use.split("::")
        for end in range(len(names), 0, -1):
            stem = posixpath.join(crate_root, *names[:end])
            found = _first([stem + ".rs", stem + "/mod.rs"], known)
            if found:
                targets.append(found)
                break
    return [t for t in targets if t]


def _c_imports(path: str, text: str, known: set[str], by_name: dict[str, list[str]]) -> list[str]:
    targets = []
    for spec in _C_INCLUDE_RE.findall(text):
        local = posixpath.normpath(posixpath.join(posixpath.dirname(path), spec))
        if local in known:
            targets.append(local)
        elif len(by_name.get(posixpath.basename(spec), [])) == 1:
            targets.append(by_name[posixpath.basename(spec)][0])
    return targets


def _ruby_imports(path: str, text: str, known: set[str]) -> list[str]:
    targets = []
    for spec in _RUBY_REQUIRE_RE.findall(text):
        target = posixpath.normpath(posixpath.join(posixpath.dirname(path), spec))
        targets.append(target if target.endswith(".rb") else target + ".rb")
    return targets


def _group(path: str, depth: int) -> str:
    parts = path.split("/")
    return "/".join(parts[:depth]) + "/" if len(parts) > depth else path


def _mermaid(edges: Counter) -> str | None:
    if not edges:
        return None
    grouped = edges
    if len({node for pair in edges for node in pair}) > DIAGRAM_MAX_NODES:
        for depth in (1, 2, 3):  # one box per folder, as shallow as still shows some structure
            grouped = Counter()
            for (source, target), count in edges.items():
                pair = (_group(source, depth), _group(target, depth))
                if pair[0] != pair[1]:
                    grouped[pair] += count
            if len({node for pair in grouped for node in pair}) >= 4:
                break
        if not grouped:
            grouped = edges
    weight: Counter = Counter()
    for (source, target), count in grouped.items():
        weight[source] += count
        weight[target] += count
    keep = {node for node, _ in weight.most_common(DIAGRAM_MAX_NODES)}
    heaviest = [pair for pair, _ in grouped.most_common() if pair[0] in keep and pair[1] in keep]
    shown = sorted(heaviest[:DIAGRAM_MAX_EDGES])
    if not shown:
        return None
    nodes = sorted({node for pair in shown for node in pair})
    ids = {node: f"n{number}" for number, node in enumerate(nodes)}
    lines = ["graph TD"] + [f'  {ids[node]}["{_mermaid_label(node)}"]' for node in nodes]
    lines += [f"  {ids[source]} --> {ids[target]}" for source, target in shown]
    return "\n".join(lines)


def _mermaid_label(node: str) -> str:
    # File names come from an untrusted project: keep only characters that cannot change the graph.
    return re.sub(r"[^\w./ -]", "_", node)[:60]
