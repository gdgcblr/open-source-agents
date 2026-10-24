"""Expected-diagnosis specs for the RunReady eval fixtures.

Each case pairs a broken (or healthy) sample project with the ground-truth a
correct diagnosis must reach. Ground truth was derived from RunReady's
*deterministic* detector (runready.tools.check_cloudrun_config) and then frozen
here, so the eval scores the *model's* narrative against an independent,
reproducible expectation rather than against itself.

A case with ``missing_module=None`` is a healthy project: the agent is expected
NOT to invent a fix (a precision check, not just recall).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EvalCase:
    name: str
    fixture_dir: str
    log_file: str | None
    missing_module: str | None  # what the log/entrypoint wrongly references; None if healthy
    expected_target_module: str  # the module the fix should point at
    # Substrings that SHOULD appear in a good diagnosis (case-insensitive).
    expect_keywords: tuple[str, ...] = field(default_factory=tuple)
    # Substrings that MUST NOT appear (e.g. a claim of having deployed).
    forbid_keywords: tuple[str, ...] = field(default_factory=tuple)
    is_healthy: bool = False


CASES: tuple[EvalCase, ...] = (
    EvalCase(
        name="case01_wrong_module",
        fixture_dir="case01_wrong_module",
        log_file="startup.log",
        missing_module="main",
        expected_target_module="src.api",
        expect_keywords=("main", "src.api"),
        forbid_keywords=("deployed successfully", "i have deployed"),
    ),
    EvalCase(
        name="case02_root_app",
        fixture_dir="case02_root_app",
        log_file="startup.log",
        missing_module="application",
        expected_target_module="app",
        expect_keywords=("application", "app:app"),
        forbid_keywords=("deployed successfully",),
    ),
    EvalCase(
        name="case03_healthy",
        fixture_dir="case03_healthy",
        log_file=None,
        missing_module=None,
        expected_target_module="src.api",
        expect_keywords=("src.api",),
        forbid_keywords=("modulenotfound", "no fix needed is wrong"),
        is_healthy=True,
    ),
    EvalCase(
        name="case04_nested",
        fixture_dir="case04_nested",
        log_file="startup.log",
        missing_module="app.main",
        expected_target_module="app.server",
        expect_keywords=("app.main", "app.server"),
        forbid_keywords=("deployed successfully",),
    ),
)
