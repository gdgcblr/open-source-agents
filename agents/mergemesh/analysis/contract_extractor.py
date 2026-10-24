"""Deterministic REST JSON & Python AST contract extractor and comparator."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any

from domain.models import ContractComparison, ContractFieldChange, ContractFieldInfo


class ContractAnalysisError(ValueError):
    """Raised when contract data is missing, malformed, or cannot be extracted."""


def _json_type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _normalize_identifier(name: str) -> str:
    """Normalize snake_case and camelCase field names for heuristic rename matching."""
    leaf = name.split(".")[-1]
    return re.sub(r"[_\-\s]", "", leaf).lower()


def _extract_fields_recursive(
    obj: dict[str, Any],
    source_path: str,
    required_set: set[str],
    prefix: str = "",
) -> dict[str, ContractFieldInfo]:
    fields: dict[str, ContractFieldInfo] = {}
    for key, val in obj.items():
        if not isinstance(key, str):
            continue
        path = f"{prefix}.{key}" if prefix else key
        jtype = _json_type_name(val)
        fields[path] = ContractFieldInfo(
            field_path=path,
            json_type=jtype,
            sample_value=val if not isinstance(val, (dict, list)) else f"<{jtype}>",
            source_path=source_path,
            required=(path in required_set or key in required_set),
        )
        if isinstance(val, dict):
            nested = _extract_fields_recursive(val, source_path, required_set, prefix=path)
            fields.update(nested)
    return fields


def _placeholder_for_annotation(ann_node: ast.AST | None) -> Any:
    """Return a sample Python value corresponding to a Python type annotation node."""
    if ann_node is None:
        return "sample"
    if isinstance(ann_node, ast.Name):
        t = ann_node.id.lower()
        if t in {"int", "integer"}:
            return 0
        if t in {"float", "decimal", "number"}:
            return 0.0
        if t in {"bool", "boolean"}:
            return False
        if t in {"list", "sequence", "set", "tuple"}:
            return []
        if t in {"dict", "mapping"}:
            return {}
        return "sample"
    return "sample"


def _eval_ast_node_with_env(node: ast.AST, env: dict[str, Any]) -> Any:
    """Evaluate a literal or simple variable reference AST node into a sample value."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id in env:
            return env[node.id]
        return "sample"
    if isinstance(node, ast.Dict):
        out: dict[str, Any] = {}
        for k_node, v_node in zip(node.keys, node.values):
            if isinstance(k_node, ast.Constant) and isinstance(k_node.value, str) and v_node is not None:
                out[k_node.value] = _eval_ast_node_with_env(v_node, env)
        return out
    if isinstance(node, (ast.List, ast.Tuple)):
        return [_eval_ast_node_with_env(el, env) for el in node.elts]
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub) and isinstance(node.operand, ast.Constant):
        if isinstance(node.operand.value, (int, float)):
            return -node.operand.value
    return "sample"


def extract_contract_from_python_source(
    source_code: str,
    source_label: str = "provider.py",
) -> tuple[dict[str, Any], set[str]]:
    """Extract a REST response dictionary contract from Python provider source code via AST."""
    if not source_code or not source_code.strip():
        raise ContractAnalysisError(f"Python contract source is empty: {source_label}")

    try:
        tree = ast.parse(source_code, filename=source_label)
    except SyntaxError as exc:
        raise ContractAnalysisError(
            f"Syntax error in Python provider source {source_label} (line {exc.lineno}): {exc.msg}"
        ) from exc

    # 1. Search functions for returned dictionary literals (`return {"key": ...}`)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            param_env: dict[str, Any] = {}
            args = node.args.args
            defaults = node.args.defaults
            default_offset = len(args) - len(defaults)
            for idx, arg in enumerate(args):
                if idx >= default_offset:
                    def_node = defaults[idx - default_offset]
                    param_env[arg.arg] = _eval_ast_node_with_env(def_node, {})
                else:
                    param_env[arg.arg] = _placeholder_for_annotation(arg.annotation)

            # Also track simple local variable assignments inside the function body
            for stmt in node.body:
                if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
                    param_env[stmt.targets[0].id] = _eval_ast_node_with_env(stmt.value, param_env)
                elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name) and stmt.value is not None:
                    param_env[stmt.target.id] = _eval_ast_node_with_env(stmt.value, param_env)

            for sub in ast.walk(node):
                if isinstance(sub, ast.Return) and isinstance(sub.value, ast.Dict):
                    extracted = _eval_ast_node_with_env(sub.value, param_env)
                    if isinstance(extracted, dict) and len(extracted) > 0:
                        return extracted, set()

    # 2. Search classes (Pydantic BaseModel / TypedDict / dataclass) for annotated fields
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            class_fields: dict[str, Any] = {}
            req_fields: set[str] = set()
            for stmt in node.body:
                if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                    fname = stmt.target.id
                    if fname.startswith("_"):
                        continue
                    if stmt.value is not None:
                        class_fields[fname] = _eval_ast_node_with_env(stmt.value, {})
                    else:
                        class_fields[fname] = _placeholder_for_annotation(stmt.annotation)
                        req_fields.add(fname)
            if class_fields:
                return class_fields, req_fields

    raise ContractAnalysisError(
        f"Could not extract a JSON/dict response contract from Python file '{source_label}'. "
        "Expected a function returning a dict literal or an annotated model class."
    )


def parse_contract_content(raw_text: str, source_label: str) -> tuple[dict[str, Any], set[str]]:
    """Parse contract fields from either a JSON snapshot/schema string or Python source code."""
    if not raw_text or not raw_text.strip():
        raise ContractAnalysisError(f"Contract content is empty: {source_label}")

    lower_label = source_label.lower()
    if lower_label.endswith(".py"):
        return extract_contract_from_python_source(raw_text, source_label=source_label)

    if not lower_label.endswith(".json"):
        raise ContractAnalysisError(
            f"Unsupported contract file format for '{source_label}'. Supported formats: .json, .py"
        )

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ContractAnalysisError(
            f"Malformed JSON in contract {source_label} (line {exc.lineno}): {exc.msg}"
        ) from exc

    if not isinstance(parsed, dict):
        raise ContractAnalysisError(
            f"Unsupported contract root type '{_json_type_name(parsed)}' in {source_label}; expected JSON object."
        )

    if len(parsed) == 0:
        raise ContractAnalysisError(f"Contract JSON object in {source_label} contains no fields.")

    explicit_required: set[str] = set()
    if "$schema" in parsed or ("properties" in parsed and isinstance(parsed.get("properties"), dict)):
        req_list = parsed.get("required", [])
        if isinstance(req_list, list):
            explicit_required.update(str(r) for r in req_list)
        props = parsed.get("properties", {})
        if not props:
            raise ContractAnalysisError(f"JSON Schema in {source_label} has an empty 'properties' map.")
        sample_obj: dict[str, Any] = {}
        for k, v in props.items():
            if isinstance(v, dict) and "type" in v:
                t = v["type"]
                sample_obj[k] = v.get(
                    "example",
                    "" if t == "string" else (0 if t in ("integer", "number") else (False if t == "boolean" else {})),
                )
            else:
                sample_obj[k] = v
        return sample_obj, explicit_required

    return parsed, explicit_required


def load_contract_json(file_path: Path) -> tuple[dict[str, Any], set[str]]:
    """Load and validate a contract file (.json or .py) from disk."""
    if not file_path.exists() or not file_path.is_file():
        raise ContractAnalysisError(f"Contract file not found: {file_path}")

    try:
        raw_text = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ContractAnalysisError(f"Unable to read contract file {file_path}: {exc}") from exc

    return parse_contract_content(raw_text, source_label=file_path.name)


def compare_contracts(
    before_data: dict[str, Any],
    after_data: dict[str, Any],
    before_path: str = "contracts/provider_before.json",
    after_path: str = "contracts/provider_after.json",
    required_fields: list[str] | None = None,
    before_raw_content: str = "",
    after_raw_content: str = "",
) -> ContractComparison:
    """Compare before and after REST JSON contracts deterministically."""
    if not isinstance(before_data, dict) or not isinstance(after_data, dict):
        raise ContractAnalysisError("Both before and after contracts must be JSON objects (dicts).")

    req_set = set(required_fields or [])
    before_fields = _extract_fields_recursive(before_data, before_path, req_set)
    after_fields = _extract_fields_recursive(after_data, after_path, req_set)

    before_keys = set(before_fields.keys())
    after_keys = set(after_fields.keys())

    removed = sorted(before_keys - after_keys)
    added = sorted(after_keys - before_keys)

    # Identify candidate renames among removed and added fields
    rename_candidates: dict[str, str] = {}
    used_added: set[str] = set()
    for rem_key in removed:
        rem_info = before_fields[rem_key]
        rem_norm = _normalize_identifier(rem_key)
        rem_parent = ".".join(rem_key.split(".")[:-1])

        best_match: str | None = None
        for add_key in added:
            if add_key in used_added:
                continue
            add_info = after_fields[add_key]
            add_parent = ".".join(add_key.split(".")[:-1])
            if rem_parent != add_parent:
                continue
            add_norm = _normalize_identifier(add_key)
            if rem_norm == add_norm and rem_norm != "":
                best_match = add_key
                break
            if (
                rem_info.json_type == add_info.json_type
                and rem_info.sample_value is not None
                and rem_info.sample_value != ""
                and rem_info.sample_value != "sample"
                and rem_info.sample_value == add_info.sample_value
            ):
                best_match = add_key
                break

        if best_match:
            rename_candidates[rem_key] = best_match
            used_added.add(best_match)

    type_changes: list[ContractFieldChange] = []
    field_changes: list[ContractFieldChange] = []
    missing_required: list[str] = []

    for r_field in req_set:
        if r_field not in after_fields:
            missing_required.append(r_field)
    missing_required = sorted(set(missing_required))

    for key in sorted(before_keys | after_keys):
        b_info = before_fields.get(key)
        a_info = after_fields.get(key)
        is_req = key in req_set or (b_info.required if b_info else False)

        if b_info and not a_info:
            candidate = rename_candidates.get(key)
            impact = (
                f"BREAKING CANDIDATE: Field removed (candidate rename to '{candidate}')"
                if candidate
                else ("BREAKING: Required field removed" if is_req else "BREAKING CANDIDATE: Field removed")
            )
            field_changes.append(
                ContractFieldChange(
                    field_path=key,
                    change_type="removed",
                    before_type=b_info.json_type,
                    after_type=None,
                    before_value=b_info.sample_value,
                    after_value=None,
                    replacement_candidate=candidate,
                    required=is_req,
                    impact=impact,
                )
            )
        elif a_info and not b_info:
            reverse_rename = next((old for old, new in rename_candidates.items() if new == key), None)
            impact = (
                f"Added field (candidate replacement for '{reverse_rename}')"
                if reverse_rename
                else "Compatible addition (non-breaking)"
            )
            field_changes.append(
                ContractFieldChange(
                    field_path=key,
                    change_type="added",
                    before_type=None,
                    after_type=a_info.json_type,
                    before_value=None,
                    after_value=a_info.sample_value,
                    replacement_candidate=None,
                    required=is_req,
                    impact=impact,
                )
            )
        elif b_info and a_info:
            if b_info.json_type != a_info.json_type:
                change = ContractFieldChange(
                    field_path=key,
                    change_type="type_changed",
                    before_type=b_info.json_type,
                    after_type=a_info.json_type,
                    before_value=b_info.sample_value,
                    after_value=a_info.sample_value,
                    required=is_req,
                    impact=f"BREAKING: Incompatible type change ({b_info.json_type} -> {a_info.json_type})",
                )
                type_changes.append(change)
                field_changes.append(change)
            else:
                field_changes.append(
                    ContractFieldChange(
                        field_path=key,
                        change_type="unchanged",
                        before_type=b_info.json_type,
                        after_type=a_info.json_type,
                        before_value=b_info.sample_value,
                        after_value=a_info.sample_value,
                        required=is_req,
                        impact="Unchanged (compatible)",
                    )
                )

    for req_missing in missing_required:
        if req_missing not in before_keys and req_missing not in after_keys:
            field_changes.append(
                ContractFieldChange(
                    field_path=req_missing,
                    change_type="missing_required",
                    before_type="required",
                    after_type=None,
                    required=True,
                    impact="BREAKING: Required field missing from provider contract",
                )
            )

    is_breaking = bool(removed or type_changes or missing_required)

    if not before_raw_content:
        before_raw_content = json.dumps(before_data, indent=2)
    if not after_raw_content:
        after_raw_content = json.dumps(after_data, indent=2)

    return ContractComparison(
        provider_before_path=before_path,
        provider_after_path=after_path,
        before_fields=before_fields,
        after_fields=after_fields,
        removed_fields=removed,
        added_fields=added,
        type_changes=type_changes,
        missing_required_fields=missing_required,
        rename_candidates=rename_candidates,
        field_changes=field_changes,
        is_breaking_candidate=is_breaking,
        before_raw_content=before_raw_content,
        after_raw_content=after_raw_content,
    )


def compare_contract_files(
    before_file: Path,
    after_file: Path,
    before_rel_path: str = "contracts/provider_before.json",
    after_rel_path: str = "contracts/provider_after.json",
    required_fields: list[str] | None = None,
) -> ContractComparison:
    """Load two contract files (.json or .py) from disk and compare them."""
    if not before_file.exists() or not before_file.is_file():
        raise ContractAnalysisError(f"Contract file not found: {before_file}")
    if not after_file.exists() or not after_file.is_file():
        raise ContractAnalysisError(f"Contract file not found: {after_file}")

    before_raw = before_file.read_text(encoding="utf-8")
    after_raw = after_file.read_text(encoding="utf-8")

    before_data, before_req = parse_contract_content(before_raw, source_label=before_file.name)
    after_data, after_req = parse_contract_content(after_raw, source_label=after_file.name)
    combined_req = sorted(set(required_fields or []) | before_req | after_req)
    return compare_contracts(
        before_data=before_data,
        after_data=after_data,
        before_path=before_rel_path,
        after_path=after_rel_path,
        required_fields=combined_req,
        before_raw_content=before_raw,
        after_raw_content=after_raw,
    )
