"""Checks for environment variable drift and paid API disclosures (E01, E02)."""

from __future__ import annotations

import ast
import re
from typing import Any

from merge_ready.model import Finding, RuleResult, Severity, Verdict
from merge_ready.project import ProjectContext

SYSTEM_ENV_VARS = {
    "PATH",
    "HOME",
    "USER",
    "USERNAME",
    "SHELL",
    "PYTHONPATH",
    "PYTHONUNBUFFERED",
    "TEMP",
    "TMP",
    "PWD",
    "TERM",
    "NODE_ENV",
    "PORT",
    "DEBUG",
    "HOST",
}

PAID_PROVIDER_SDKS = {
    "google.genai": "Google Gemini API (google-genai)",
    "google.generativeai": "Google Gemini API (legacy google-generativeai)",
    "openai": "OpenAI API",
    "anthropic": "Anthropic API",
    "cohere": "Cohere API",
    "mistralai": "Mistral AI",
    "groq": "Groq API",
    "tavily": "Tavily Search API",
    "serpapi": "SerpApi",
    "pinecone": "Pinecone Vector DB",
}

DISCLOSURE_KEYWORDS = [
    "api key",
    "api_key",
    "billing",
    "cost",
    "paid",
    "free tier",
    "pricing",
    "quota",
    "token",
    "credentials",
]


def extract_python_env_vars(tree: ast.AST) -> set[tuple[str, int]]:
    """Extract environment variable names read in Python AST."""
    env_vars: set[tuple[str, int]] = set()

    for node in ast.walk(tree):
        # os.environ['KEY']
        if isinstance(node, ast.Subscript):
            if isinstance(node.value, ast.Attribute) and node.value.attr == "environ":
                if isinstance(node.value.value, ast.Name) and node.value.value.id == "os":
                    if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
                        env_vars.add((node.slice.value, node.lineno))

        # os.environ.get('KEY') or os.getenv('KEY')
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "get":
                if isinstance(func.value, ast.Attribute) and func.value.attr == "environ":
                    if isinstance(func.value.value, ast.Name) and func.value.value.id == "os":
                        if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                            env_vars.add((node.args[0].value, node.lineno))
            elif isinstance(func, ast.Attribute) and func.attr == "getenv":
                if isinstance(func.value, ast.Name) and func.value.id == "os":
                    if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                        env_vars.add((node.args[0].value, node.lineno))

    return env_vars


def extract_js_env_vars(content: str) -> set[tuple[str, int]]:
    """Extract environment variable names from JS/TS content."""
    env_vars: set[tuple[str, int]] = set()
    lines = content.splitlines()
    dot_pat = re.compile(r"process\.env\.([a-zA-Z0-9_]+)")
    sub_pat = re.compile(r"process\.env\[['\"]([a-zA-Z0-9_]+)['\"]\]")

    for idx, line in enumerate(lines, 1):
        for m in dot_pat.finditer(line):
            env_vars.add((m.group(1), idx))
        for m in sub_pat.finditer(line):
            env_vars.add((m.group(1), idx))

    return env_vars


def parse_env_example(content: str) -> set[str]:
    """Parse environment variable names from .env.example, supporting commented examples."""
    documented = set()
    pattern = re.compile(r"^\s*#?\s*([A-Za-z_][A-Za-z0-9_]*)\s*=")
    for line in content.splitlines():
        line_strip = line.strip()
        if not line_strip or line_strip.startswith("# ---") or line_strip.startswith("# Copy this"):
            continue
        m = pattern.match(line)
        if m:
            var_name = m.group(1).strip()
            # Ignore markdown headings or generic comment words
            if var_name not in ("NOTE", "TIP", "WARNING", "IMPORTANT", "CAUTION"):
                documented.add(var_name)
    return documented


def check_e01(ctx: ProjectContext, config: dict[str, Any]) -> RuleResult:
    """E01: Identify environment variables read in code and compare with documentation."""
    rule_id = "E01"
    name = "Environment Variable Drift"
    source = config.get("source_rule", "CONTRIBUTING.md Step 7")

    # Collect documented variables from .env.example and README.md
    documented_vars: set[str] = set()
    env_example_content = ctx.read_text(".env.example")
    if env_example_content:
        documented_vars.update(parse_env_example(env_example_content))

    readme_content = ctx.read_text("README.md")
    if readme_content:
        # Search specifically inside 'Configuration & Environment Variables' section for uppercase VAR_NAME
        sec_match = re.search(
            r"##\s*Configuration & Environment Variables(.*?)(?:##|\Z)",
            readme_content,
            re.DOTALL | re.IGNORECASE,
        )
        config_sec = sec_match.group(1) if sec_match else ""
        for m in re.finditer(r"`([A-Z_][A-Z0-9_]{2,})`", config_sec):
            documented_vars.add(m.group(1))

    # Scan code files for env reads
    used_vars: dict[str, list[tuple[str, int]]] = {}
    for rel_path in ctx.files:
        posix = rel_path.as_posix()
        if rel_path.suffix == ".py":
            txt = ctx.read_text(rel_path)
            if txt:
                try:
                    tree = ast.parse(txt, filename=posix)
                    for var, lineno in extract_python_env_vars(tree):
                        if var not in SYSTEM_ENV_VARS:
                            used_vars.setdefault(var, []).append((posix, lineno))
                except Exception:
                    pass
        elif rel_path.suffix in (".js", ".ts", ".jsx", ".tsx"):
            txt = ctx.read_text(rel_path)
            if txt:
                for var, lineno in extract_js_env_vars(txt):
                    if var not in SYSTEM_ENV_VARS:
                        used_vars.setdefault(var, []).append((posix, lineno))

    if not used_vars and not documented_vars:
        return RuleResult(
            rule_id=rule_id,
            name=name,
            verdict=Verdict.NA,
            reason="Project does not reference or declare environment variables.",
        )

    findings: list[Finding] = []

    # Check for missing variables (in code, but undocumented)
    for var, locations in used_vars.items():
        if var not in documented_vars:
            loc_str = ", ".join(f"{p}:{l}" for p, l in locations[:3])
            primary_path, primary_line = locations[0]
            findings.append(
                Finding(
                    rule_id=rule_id,
                    severity=Severity.ERROR,
                    message=f"Undocumented environment variable '{var}' read in source code.",
                    path=primary_path,
                    line=primary_line,
                    evidence=f"Variable '{var}' referenced at {loc_str} but missing from .env.example and README.md.",
                    fix=f"Document '{var}' with a placeholder in .env.example and describe it in README.md.",
                    source_rule=source,
                )
            )

    # Check for stale variables (in .env.example, but not read in code)
    for doc_var in documented_vars:
        if doc_var not in used_vars and doc_var not in SYSTEM_ENV_VARS:
            # Only warn for stale variables if there is some code in the project
            has_code = any(p.suffix in (".py", ".js", ".ts") for p in ctx.files)
            if has_code:
                findings.append(
                    Finding(
                        rule_id=rule_id,
                        severity=Severity.WARNING,
                        message=f"Environment variable '{doc_var}' documented in .env.example is not referenced in source code.",
                        path=".env.example",
                        evidence=f"Variable '{doc_var}' is declared but not read by any discovered source file.",
                        fix=f"Remove '{doc_var}' if obsolete, or verify the variable name matches code usage.",
                        source_rule=source,
                    )
                )

    has_errors = any(f.severity == Severity.ERROR for f in findings)
    verdict = Verdict.FAIL if has_errors else (Verdict.WARN if findings else Verdict.PASS)
    return RuleResult(rule_id=rule_id, name=name, verdict=verdict, findings=findings)


def check_e02(ctx: ProjectContext, config: dict[str, Any]) -> RuleResult:
    """E02: Check that imports of paid model provider SDKs disclose API requirements."""
    rule_id = "E02"
    name = "Paid API and Model Disclosure"
    source = config.get("source_rule", "CONTRIBUTING.md Quality & Security Standards")

    # Detect provider imports in code
    detected_providers: dict[str, list[str]] = {}
    for rel_path in ctx.files:
        if rel_path.suffix == ".py":
            txt = ctx.read_text(rel_path)
            if txt:
                try:
                    tree = ast.parse(txt)
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Import):
                            for alias in node.names:
                                for prov in PAID_PROVIDER_SDKS:
                                    if alias.name == prov or alias.name.startswith(prov + "."):
                                        detected_providers.setdefault(prov, []).append(rel_path.as_posix())
                        elif isinstance(node, ast.ImportFrom):
                            if node.module:
                                for prov in PAID_PROVIDER_SDKS:
                                    if node.module == prov or node.module.startswith(prov + "."):
                                        detected_providers.setdefault(prov, []).append(rel_path.as_posix())
                except Exception:
                    pass

    if not detected_providers:
        return RuleResult(
            rule_id=rule_id,
            name=name,
            verdict=Verdict.NA,
            reason="No known paid model provider SDKs imported.",
        )

    readme_content = ctx.read_text("README.md") or ""
    readme_lower = readme_content.lower()

    has_disclosure = any(kw in readme_lower for kw in DISCLOSURE_KEYWORDS)
    findings: list[Finding] = []

    if not has_disclosure:
        prov_list = ", ".join(PAID_PROVIDER_SDKS[p] for p in detected_providers)
        findings.append(
            Finding(
                rule_id=rule_id,
                severity=Severity.WARNING,
                message=f"Project imports model provider SDK(s) ({prov_list}) without clear API key/cost disclosure in README.md.",
                path="README.md",
                evidence=f"Discovered provider SDK imports in: {', '.join(sorted(set(sum(detected_providers.values(), []))))}",
                fix="State required API keys, model assumptions, and free-tier or billing considerations in README.md.",
                source_rule=source,
            )
        )

    verdict = Verdict.WARN if findings else Verdict.PASS
    return RuleResult(rule_id=rule_id, name=name, verdict=verdict, findings=findings)
