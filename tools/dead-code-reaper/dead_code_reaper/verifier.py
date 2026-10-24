"""Prove removals by deleting them in a copy of the project and running checks.

All work happens in a temporary copy; the original project is never touched
here. Removals are tried in batches: if a whole batch can go with the checks
still passing, all of it is accepted in one run. If not, the batch is split in
half and each half is tried, until the removals that break things are found.

The check is the project's test suite. A project with no tests gets a weaker
check (every file compiles and every package module imports), and removals
that only pass that check are marked unverified.

Every check run has a time limit, and the total number of runs is capped, so
verification always ends. Removals not reached before the cap are unverified.
"""
from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .analyzer import ScanResult
from .edits import apply_removals
from .model import MIN_CONFIDENCE_TICKED, Removal

COPY_IGNORED = {".git", ".hg", ".svn", "node_modules", "__pycache__", ".tox", ".nox",
                ".mypy_cache", ".pytest_cache", ".ruff_cache", ".venv", "venv", "reaper-out"}

# Run in the project copy when there are no tests: compile everything, then
# import every module that lives in a package. Top-level scripts are only
# compiled, because importing them would run them.
IMPORT_CHECK = r'''
import importlib, os, sys, traceback
root = os.getcwd()
skip = {".git", ".venv", "venv", "node_modules", "__pycache__", "build", "dist", ".tox"}
sys.path[:0] = [root, os.path.join(root, "src")]
failed = False
modules = []
for dirpath, dirnames, filenames in os.walk(root):
    dirnames[:] = [d for d in dirnames if d not in skip and not d.startswith(".")]
    for fn in filenames:
        if not fn.endswith(".py"):
            continue
        path = os.path.join(dirpath, fn)
        try:
            with open(path, encoding="utf-8") as fh:
                compile(fh.read(), path, "exec")
        except Exception as exc:
            print("compile failed:", path, exc); failed = True
        rel = os.path.relpath(path, root)
        parts = rel[:-3].split(os.sep)
        if parts[-1] == "__init__":
            parts = parts[:-1]
        if any(p in ("tests", "test") for p in parts) or fn.startswith("test_") or fn == "conftest.py":
            continue
        base = os.path.join(root, "src") if parts and parts[0] == "src" else root
        if parts and parts[0] == "src":
            parts = parts[1:]
        d, ok = base, bool(parts)
        for p in parts[:-1] if fn != "__init__.py" else parts:
            d = os.path.join(d, p)
            if not os.path.exists(os.path.join(d, "__init__.py")):
                ok = False
        if ok and (fn != "__init__.py" or parts) and os.path.exists(os.path.join(base, parts[0], "__init__.py")):
            modules.append(".".join(parts))
for m in sorted(set(modules)):
    try:
        importlib.import_module(m)
    except BaseException:
        print("import failed:", m); traceback.print_exc(); failed = True
sys.exit(1 if failed else 0)
'''


@dataclass
class VerifyResult:
    check_mode: str                   # "tests" or "import"
    baseline_passed: bool
    baseline_output: str = ""
    runs: int = 0
    seconds: float = 0.0
    removals: list[Removal] = field(default_factory=list)  # all, with status set
    final_files: dict[str, str | None] = field(default_factory=dict)


def default_test_command() -> list[str]:
    return [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider"]


def parse_command(cmd) -> list[str]:
    if cmd is None:
        return default_test_command()
    if isinstance(cmd, list):
        return cmd
    return shlex.split(cmd, posix=os.name != "nt")


def check_command(check_mode: str, test_cmd) -> list[str]:
    if check_mode == "import":
        return [sys.executable, "-c", IMPORT_CHECK]
    return parse_command(test_cmd)


class Workspace:
    """A temporary copy of the project that removals are applied to."""

    def __init__(self, root: str, sources: dict[str, str]):
        self.sources = sources
        self.tmp = Path(tempfile.mkdtemp(prefix="dead-code-reaper-"))
        self.root = self.tmp / "project"

        def ignore(directory, names):
            out = {n for n in names if n in COPY_IGNORED}
            out |= {n for n in names if (Path(directory) / n / "pyvenv.cfg").exists()}
            return out

        shutil.copytree(root, self.root, ignore=ignore)
        self.current: dict[str, str | None] = {}

    def materialize(self, removals: list[Removal]) -> bool:
        desired = apply_removals(self.sources, removals)
        if desired is None:
            return False
        for rel in set(desired) | set(self.current):
            target = desired.get(rel, self.sources[rel])
            if self.current.get(rel, self.sources[rel]) == target:
                continue
            path = self.root / rel
            if target is None:
                path.unlink(missing_ok=True)
            else:
                path.write_text(target, encoding="utf-8")
            if target == self.sources[rel]:
                self.current.pop(rel, None)
            else:
                self.current[rel] = target
        return True

    def env(self) -> dict:
        # Put the copy first on the import path, so an editable install
        # (`pip install -e .`) of the original can't shadow it.
        paths = [str(self.root), str(self.root / "src"), os.environ.get("PYTHONPATH", "")]
        return dict(os.environ, PYTHONDONTWRITEBYTECODE="1",
                    PYTHONPATH=os.pathsep.join(p for p in paths if p))

    def top_packages(self) -> list[str]:
        names = []
        for base in (self.root, self.root / "src"):
            if base.is_dir():
                names += [d.name for d in base.iterdir()
                          if (d / "__init__.py").is_file() and d.name not in ("tests", "test")]
        return sorted(set(names))

    def imports_from_copy(self) -> tuple[bool, str]:
        """Check that the project's packages are imported from this copy, not elsewhere."""
        packages = self.top_packages()
        if not packages:
            return True, ""
        code = ("import importlib, os, sys\n"
                "for n in sys.argv[1:]:\n"
                "    try:\n        m = importlib.import_module(n)\n"
                "    except BaseException:\n        continue\n"
                "    print(n, os.path.realpath(getattr(m, '__file__', '') or ''))\n")
        try:
            proc = subprocess.run([sys.executable, "-c", code, *packages], cwd=self.root,
                                  capture_output=True, text=True, timeout=120, env=self.env())
        except subprocess.TimeoutExpired:
            return True, ""
        root = os.path.realpath(self.root)
        for line in proc.stdout.splitlines():
            name, _, path = line.partition(" ")
            if path and not path.startswith(root + os.sep):
                return False, f"package `{name}` is imported from {path}, not from the copy being checked"
        return True, ""

    def run(self, cmd: list[str], timeout: int) -> tuple[bool, str]:
        env = self.env()
        try:
            proc = subprocess.run(cmd, cwd=self.root, capture_output=True, text=True,
                                  timeout=timeout, env=env)
        except subprocess.TimeoutExpired:
            return False, f"timed out after {timeout}s"
        except FileNotFoundError as exc:
            return False, f"could not run the check: {exc}"
        return proc.returncode == 0, (proc.stdout + proc.stderr)[-4000:]

    def cleanup(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


def keep_closure(removals: list[Removal], kept: set[str]) -> tuple[set[str], dict[str, str]]:
    """Expand a set of kept keys with everything they depend on.

    Returns the expanded set and, for each added key, the kept key that caused it.
    """
    kept = set(kept)
    why: dict[str, str] = {}
    changed = True
    while changed:
        changed = False
        for r in removals:
            if r.key in kept:
                continue
            cause = next((k for k in r.used_by if k in kept), None)
            if cause:
                kept.add(r.key)
                why[r.key] = cause
                changed = True
    return kept, why


def hold_dependencies(removals: list[Removal]):
    """Make the default selection consistent: anything used by a removal that starts
    kept starts kept too (with held_by saying why)."""
    for r in removals:
        r.held_by = None
    start_kept = {r.key for r in removals if r.default_keep}
    _, why = keep_closure(removals, start_kept)
    for r in removals:
        if r.key in why:
            r.held_by = why[r.key]


def verify(scan: ScanResult, test_cmd=None, timeout: int = 600, max_runs: int = 60,
           log: Callable[[str], None] = print) -> VerifyResult:
    check_mode = "tests" if (test_cmd or scan.has_tests) else "import"
    cmd = check_command(check_mode, test_cmd)
    started = time.time()
    removals = scan.removals
    ws = Workspace(scan.root, scan.sources)
    try:
        if check_mode == "import":
            log("No tests found: falling back to a compile and import check. "
                "Removals will be marked unverified.")
        log(f"Baseline check: {'tests' if check_mode == 'tests' else 'compile and import'}")
        ok, output = ws.run(cmd, timeout)
        result = VerifyResult(check_mode=check_mode, baseline_passed=ok,
                              baseline_output=output, runs=1, removals=removals)
        if ok:
            ok, problem = ws.imports_from_copy()
            if not ok:
                result.baseline_passed = False
                result.baseline_output = (
                    f"Can't verify safely: {problem}. Checks would test the original code "
                    "instead of the edited copy. If your test command changes how imports "
                    "work, make it import the project from the current directory.")
                log(result.baseline_output)
                result.seconds = time.time() - started
                return result
        if not ok:
            log("Baseline check FAILED on the unchanged project. Fix it first; nothing was removed.")
            result.seconds = time.time() - started
            return result

        accepted: list[Removal] = []
        rejected: set[str] = set()
        out_of_budget: set[str] = set()
        ordered = sorted(removals, key=lambda r: (-r.confidence, r.path, r.start))

        def attempt(group: list[Removal]) -> bool:
            if not ws.materialize(accepted + group):
                return False
            result.runs += 1
            passed, _ = ws.run(cmd, timeout)
            return passed

        def search(group: list[Removal]):
            if not group:
                return
            if result.runs >= max_runs:
                out_of_budget.update(r.key for r in group)
                return
            if attempt(group):
                accepted.extend(group)
                log(f"  ok: {len(group)} removal{'s' if len(group) != 1 else ''}")
            elif len(group) == 1:
                rejected.add(group[0].key)
                log(f"  needed: {group[0].key}")
            else:
                log(f"  a batch of {len(group)} failed; splitting it")
                mid = len(group) // 2
                search(group[:mid])
                search(group[mid:])

        # Low-confidence removals fail more often; batching them separately keeps
        # one failure from splitting the batch of confident ones.
        # Removals used by a low-confidence one share its fate, so they go with it.
        low, _ = keep_closure(removals, {r.key for r in removals
                                         if r.confidence < MIN_CONFIDENCE_TICKED})
        search([r for r in ordered if r.key not in low])
        search([r for r in ordered if r.key in low])

        # Anything still used by kept code must be kept too.
        kept, why = keep_closure(removals, rejected | out_of_budget)
        for r in removals:
            if r.key in rejected:
                r.status, r.status_reason = "needed", "the check failed without it"
            elif r.key in out_of_budget:
                r.status, r.status_reason = "unverified", f"not checked: the limit of {max_runs} runs was reached"
            elif r.key in why:
                r.status, r.status_reason = "needed", f"used by {why[r.key]}, which is kept"
            elif check_mode == "import":
                r.status, r.status_reason = "unverified", "passed the compile and import check only (no tests)"
            else:
                r.status, r.status_reason = "verified", "the tests pass without it"
        hold_dependencies(removals)
        final = [r for r in removals if r.key not in kept]
        ws.materialize(final)
        result.final_files = dict(ws.current)
        result.seconds = time.time() - started
        return result
    finally:
        ws.cleanup()


def check_selection(root: str, sources: dict[str, str], selection: list[Removal],
                    check_mode: str, test_cmd, timeout: int) -> tuple[bool, str, dict[str, str | None]]:
    """Run the check once on exactly `selection`. Used by `apply`."""
    ws = Workspace(root, sources)
    try:
        if not ws.materialize(selection):
            return False, "the selected removals can't be applied cleanly", {}
        safe, problem = ws.imports_from_copy()
        if not safe:
            return False, f"Can't check safely: {problem}.", {}
        ok, output = ws.run(check_command(check_mode, test_cmd), timeout)
        return ok, output, dict(ws.current)
    finally:
        ws.cleanup()
