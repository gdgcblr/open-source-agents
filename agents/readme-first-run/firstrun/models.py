"""Data types shared by every stage of a FirstRun check."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Optional

# on_event(kind, message, data). Kinds used across the package:
#   stage       data={"stage": understand|attempt|investigate|repair|verify|report, "state": start|done|fail}
#   log         one raw line of sandbox output (message is the line)
#   step_start  data={"index": int, "command": str}
#   step_end    data={"index": int, "status": str, "exit_code": int|None}
#   tool_call   data={"tool": str, "args": dict}   (investigator reading files)
#   info / warn plain messages for the user
EventFn = Callable[[str, str, Optional[dict]], None]


def noop_event(kind: str, message: str, data: Optional[dict] = None) -> None:
    pass


@dataclass
class Step:
    index: int  # 1-based position in the plan
    command: str  # as written in the README, can span several lines
    kind: str = "setup"  # prerequisite | setup | configure | run | test
    section: str = ""  # README heading the command sits under
    line: Optional[int] = None  # 1-based README line where the command starts
    long_running: bool = False  # servers and UIs: pass if still alive after the watch window
    purpose: str = ""
    provided_by_firstrun: bool = False  # e.g. installing a documented prerequisite such as uv
    expect_exit: Optional[int] = None  # non-zero exit the README says is the expected result


@dataclass
class Skipped:
    command: str
    reason: str  # e.g. "windows-only", "git clone (project is already checked out)"
    line: Optional[int] = None


@dataclass
class Plan:
    steps: list[Step]
    skipped: list[Skipped] = field(default_factory=list)
    readme_path: Optional[str] = None  # relative to the project root
    required_env: list[str] = field(default_factory=list)
    expected_output: Optional[str] = None  # the README's documented example output, if any
    engine: str = "rules"  # rules | gemini
    notes: list[str] = field(default_factory=list)


@dataclass
class StepResult:
    step: Step
    status: str  # passed | failed | timeout | alive | not_run
    exit_code: Optional[int]
    output: str  # combined stdout and stderr of this step only
    duration: float

    @property
    def ok(self) -> bool:
        return self.status in ("passed", "alive")


@dataclass
class RunResult:
    """One execution of a plan inside one fresh sandbox."""

    label: str  # "as documented", "after fix 1", ...
    status: str  # passed | failed | timeout | error
    results: list[StepResult]
    duration: float
    sandbox: str  # e.g. "docker python:3.12-slim" or "local venv (python 3.12.4)"
    log: str  # full raw log, markers stripped
    error: Optional[str] = None  # sandbox level problem (docker missing, image pull failed, ...)

    @property
    def failed_step(self) -> Optional[StepResult]:
        for r in self.results:
            if r.status in ("failed", "timeout"):
                return r
        return None


@dataclass
class Edit:
    path: str  # relative to the project root
    old: str  # exact text to replace, must occur once. "" means append (or create the file)
    new: str


@dataclass
class Evidence:
    file: str
    line: Optional[int]
    note: str


@dataclass
class Diagnosis:
    # missing_dependency | undocumented_step | wrong_command | missing_file | credentials_required
    # template_leftover | dependency_pin | interactive_input | platform_issue | code_bug | unknown
    category: str
    summary: str  # one sentence a maintainer can read in a PR comment
    explanation: str = ""
    evidence: list[Evidence] = field(default_factory=list)
    edits: list[Edit] = field(default_factory=list)
    blocked: bool = False  # true when FirstRun must stop (credentials, hardware, paid service)
    missing_env: list[str] = field(default_factory=list)
    confidence: str = "medium"  # high | medium | low
    engine: str = "rules"  # rules | gemini
    trace: list[dict] = field(default_factory=list)  # investigator tool calls


@dataclass
class Round:
    number: int
    diagnosis: Diagnosis
    diff: str = ""  # cumulative unified diff against the original project
    plan: Optional[Plan] = None  # plan re-read from the patched README
    verification: Optional[RunResult] = None


@dataclass
class Report:
    project: str
    source: str
    started_at: str
    finished_at: str
    verdict: str  # passed | fixed | blocked | failed | error
    headline: str
    documented_plan: Optional[Plan]
    documented_run: Optional[RunResult]
    rounds: list[Round] = field(default_factory=list)
    final_diff: str = ""
    settings: dict = field(default_factory=dict)
    static_hints: list[str] = field(default_factory=list)
    output_check: Optional[dict] = None  # {"documented": str, "actual": str, "similarity": float}
    error: Optional[str] = None
    # time_to_first_success, documented_seconds, failed_at_step, steps_documented, skipped_lines,
    # rounds, fixes_applied, sandbox_runs, total_seconds
    metrics: dict = field(default_factory=dict)


def to_dict(obj: Any) -> Any:
    return asdict(obj)
