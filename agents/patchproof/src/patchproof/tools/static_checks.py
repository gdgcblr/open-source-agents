"""Deterministic static AST checks that inspect code snapshots without host execution."""

from __future__ import annotations

import ast
from dataclasses import dataclass

from patchproof.ingestion.snapshot import ContextSnapshot


@dataclass(frozen=True)
class StaticCheckOutcome:
    """Result of an in-memory deterministic AST check."""

    passed: bool
    exit_code: int
    summary: str
    path: str | None = None
    line_start: int | None = None
    line_end: int | None = None


def run_static_ast_retry_bound_check(
    snapshot: ContextSnapshot,
    target_path: str | None = None,
) -> StaticCheckOutcome:
    """Inspect Python AST for off-by-one retry loop bounds without executing code.

    Specifically checks retry loops where a retry counter initialized to 0 is compared
    using `<=` against `max_retries` (allowing `max_retries + 1` retries instead of
    at most `max_retries` retries).
    """
    candidates = (
        [snapshot.source_files[target_path]]
        if target_path and target_path in snapshot.source_files
        else list(snapshot.source_files.values())
    )
    if not candidates:
        return StaticCheckOutcome(
            passed=False,
            exit_code=2,
            summary="No source files available for static AST retry bound check.",
        )

    violations: list[tuple[str, int, int, str]] = []
    inspected_loops = 0

    for file_snap in candidates:
        try:
            tree = ast.parse(file_snap.content, filename=file_snap.path)
        except SyntaxError as exc:
            return StaticCheckOutcome(
                passed=False,
                exit_code=2,
                summary=f"SyntaxError in {file_snap.path}:{exc.lineno}: {exc.msg}",
                path=file_snap.path,
                line_start=exc.lineno or 1,
                line_end=exc.lineno or 1,
            )

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                zero_initialized_vars: set[str] = set()
                for stmt in ast.walk(node):
                    if isinstance(stmt, ast.Assign):
                        if isinstance(stmt.value, ast.Constant) and stmt.value.value == 0:
                            for target in stmt.targets:
                                if isinstance(target, ast.Name):
                                    zero_initialized_vars.add(target.id)

                for stmt in ast.walk(node):
                    if isinstance(stmt, ast.While) and isinstance(stmt.test, ast.Compare):
                        inspected_loops += 1
                        left = stmt.test.left
                        ops = stmt.test.ops
                        comparators = stmt.test.comparators
                        if (
                            isinstance(left, ast.Name)
                            and len(ops) == 1
                            and len(comparators) == 1
                            and isinstance(comparators[0], ast.Name)
                        ):
                            lhs_name = left.id
                            rhs_name = comparators[0].id
                            if (
                                lhs_name in zero_initialized_vars
                                and "retr" in rhs_name.lower()
                                and isinstance(ops[0], ast.LtE)
                            ):
                                line_s = stmt.lineno
                                line_e = getattr(stmt, "end_lineno", line_s) or line_s
                                violations.append(
                                    (
                                        file_snap.path,
                                        line_s,
                                        line_e,
                                        f"In function '{node.name}', loop condition "
                                        f"`while {lhs_name} <= {rhs_name}:` with "
                                        f"`{lhs_name} = 0` executes {rhs_name} + 1 retries "
                                        "(off-by-one boundary defect; "
                                        f"expected `< {rhs_name}`).",
                                    )
                                )

    if violations:
        path, line_s, line_e, msg = violations[0]
        return StaticCheckOutcome(
            passed=False,
            exit_code=1,
            summary=f"STATIC_AST_CHECK_FAILED: {msg}",
            path=path,
            line_start=line_s,
            line_end=line_e,
        )

    first_file = candidates[0]
    return StaticCheckOutcome(
        passed=True,
        exit_code=0,
        summary=(
            f"STATIC_AST_CHECK_PASSED: Inspected {inspected_loops} while-loop condition(s) "
            "across source snapshot; retry counter upper bound strictly respects max_retries."
        ),
        path=first_file.path,
        line_start=1,
        line_end=max(1, first_file.line_count),
    )
