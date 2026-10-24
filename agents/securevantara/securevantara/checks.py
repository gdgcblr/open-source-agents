"""Small deterministic Python AST checks, not vulnerability confirmation."""
import ast
import hashlib
from pathlib import Path


def deduplicate(findings):
    merged = {}
    for finding in findings:
        key = (finding["rule"], finding["path"], finding["line"], finding["evidence"])
        if key not in merged:
            merged[key] = dict(finding, provenance=list(finding["provenance"]))
        else:
            for origin in finding["provenance"]:
                if origin not in merged[key]["provenance"]:
                    merged[key]["provenance"].append(origin)
    return list(merged.values())


def check(root):
    findings, errors = [], []
    for path in sorted(Path(root).rglob("*.py")):
        relative = str(path.relative_to(root))
        if any(part in {".git", ".venv", "venv", "__pycache__"}
               for part in Path(relative).parts):
            continue
        try:
            if path.stat().st_size > 1048576:
                errors.append({"path": relative, "error": "file exceeds 1 MiB"})
                continue
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (OSError, UnicodeError, SyntaxError) as exc:
            errors.append({"path": relative, "error": type(exc).__name__})
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            if node.func.id not in {"eval", "exec"}:
                continue
            rule = "python.dynamic-" + node.func.id
            evidence = ast.get_source_segment(source, node) or node.func.id
            identity = f"{rule}:{relative}:{node.lineno}:{evidence}"
            findings.append(dict(id=hashlib.sha256(identity.encode()).hexdigest(),
                                 rule=rule, title="Dynamic Python execution",
                                 severity="info", status="needs-review",
                                 kind="source-review", path=relative, line=node.lineno,
                                 evidence=evidence, provenance=[{"engine": "securevantara-ast",
                                                               "rule": rule}]))
    return deduplicate(findings), errors
