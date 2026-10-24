"""Linter backends behind one interface, so every language reports the same rule ids.

python     -> stdlib AST rules + taint (rules.py, taint.py)
javascript -> ESLint with the rce-sentinel plugin (AST + scope-aware taint)
go         -> gosec (G204), plus regex for rules gosec does not cover
any        -> lint-style regex fallback when the real linter is not installed

Scanned files are copied into a temp dir and linted with our config passed via -c, so a
repo's own linter config and plugins are never loaded and scanned code never runs.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import ClassVar, Protocol

from rce_sentinel.models import Finding
from rce_sentinel.scanner.rules import RulePack, build_finding, scan_regex

TOOL_ROOT = Path(__file__).resolve().parents[3]
MSG_RE = re.compile(r"kind=(\w+);source=(.*);scope=(\d+-\d+)?$")


class Backend(Protocol):
    name: str

    def available(self) -> bool: ...

    def covers(self, pack: RulePack) -> set[str]: ...

    def scan(self, files: dict[str, str], pack: RulePack, allow_suppress: bool,
             timeout: float) -> list[Finding]: ...


def _stage(files: dict[str, str]) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="rce-sentinel-lint-")).resolve()
    for rel, text in files.items():
        dest = (tmp / rel).resolve()
        if tmp not in dest.parents:  # refuse ../ paths
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
    return tmp


class EslintBackend:
    name = "eslint"

    def __init__(self, root: Path | None = None):
        env = os.environ.get("RCE_SENTINEL_ESLINT_DIR")
        self.root = Path(env) if env else (root or TOOL_ROOT / "linters" / "eslint")
        self.bin = self.root / "node_modules" / "eslint" / "bin" / "eslint.js"
        self.config = self.root / "eslint.config.mjs"

    def available(self) -> bool:
        return bool(shutil.which("node")) and self.bin.exists() and self.config.exists()

    def covers(self, pack: RulePack) -> set[str]:
        return {r.id for r in pack.rules}

    def scan(self, files: dict[str, str], pack: RulePack, allow_suppress: bool,
             timeout: float) -> list[Finding]:
        tmp = _stage(files)
        try:
            res = subprocess.run(
                ["node", str(self.bin), "-c", str(self.config), "--format", "json",
                 "--no-warn-ignored", "."],
                cwd=tmp, capture_output=True, text=True, timeout=timeout, check=False)
            if res.returncode not in (0, 1):
                raise RuntimeError(f"eslint exit {res.returncode}: {res.stderr.strip()[:200]}")
            return self.parse(json.loads(res.stdout or "[]"), tmp, files, pack, allow_suppress)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    @staticmethod
    def parse(results: list[dict], tmp: Path, files: dict[str, str], pack: RulePack,
              allow_suppress: bool) -> list[Finding]:
        rules = {r.id: r for r in pack.rules}
        out = []
        for entry in results:
            rel = _relative(entry["filePath"], tmp)
            if rel not in files:
                continue
            lines = files[rel].splitlines()
            for msg in entry.get("messages", []):
                rule_id = (msg.get("ruleId") or "").removeprefix("rce-sentinel/")
                m = MSG_RE.match(msg.get("message", ""))
                if rule_id not in rules or not m:
                    continue
                kind, source, scope = m.group(1), m.group(2) or None, m.group(3)
                if kind == "constant" and rule_id != "js-string-timer":
                    continue
                span = tuple(int(x) for x in scope.split("-")) if scope else None
                out.append(build_finding(rel, lines, rules[rule_id], int(msg["line"]),
                                         "constant" if kind == "constant" else kind,
                                         f"`{source}`" if source else None,
                                         span, allow_suppress))  # type: ignore[arg-type]
        return out


class GosecBackend:
    name = "gosec"
    MAP: ClassVar[dict[str, str]] = {"G204": "go-exec-variable"}
    SHELL = re.compile(r'exec\.Command(Context)?\([^)]*"(sh|bash|/bin/sh|/bin/bash|cmd)"\s*,'
                       r'\s*"(-c|/c)"')

    def available(self) -> bool:
        return bool(shutil.which("gosec"))

    def covers(self, pack: RulePack) -> set[str]:
        return {"go-exec-variable", "go-exec-shell"}

    def scan(self, files: dict[str, str], pack: RulePack, allow_suppress: bool,
             timeout: float) -> list[Finding]:
        tmp = _stage({**files, "go.mod": "module rcesentinelscan\n\ngo 1.21\n"})
        try:
            res = subprocess.run(["gosec", "-fmt=json", "-quiet", "-no-fail", "./..."],
                                 cwd=tmp, capture_output=True, text=True, timeout=timeout,
                                 check=False)
            return self.parse(json.loads(res.stdout or "{}"), tmp, files, pack, allow_suppress)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def parse(self, data: dict, tmp: Path, files: dict[str, str], pack: RulePack,
              allow_suppress: bool) -> list[Finding]:
        rules = {r.id: r for r in pack.rules}
        out = []
        for issue in data.get("Issues") or []:
            rule_id = self.MAP.get(issue.get("rule_id", ""))
            rel = _relative(issue.get("file", ""), tmp)
            if not rule_id or rel not in files:
                continue
            line = int(str(issue.get("line", "0")).split("-")[0])
            lines = files[rel].splitlines()
            if 0 < line <= len(lines) and self.SHELL.search(lines[line - 1]):
                rule_id = "go-exec-shell"
            out.append(build_finding(rel, lines, rules[rule_id], line, "unknown", None, None,
                                     allow_suppress))
        return out


def _relative(path: str, tmp: Path) -> str:
    try:
        return Path(path).resolve().relative_to(tmp).as_posix()
    except ValueError:
        return path


BACKENDS: dict[str, type] = {"eslint": EslintBackend, "gosec": GosecBackend}


def scan_with_linter(pack: RulePack, files: dict[str, str], allow_suppress: bool,
                     timeout: float) -> tuple[list[Finding], str | None]:
    """Run the pack's linter, then regex for anything it does not cover.

    Returns findings and a degraded-mode note when the real linter was unavailable."""
    note = None
    findings: list[Finding] = []
    covered: set[str] = set()
    backend_cls = BACKENDS.get(pack.linter)
    if backend_cls is not None:
        backend = backend_cls()
        if backend.available():
            try:
                findings = backend.scan(files, pack, allow_suppress, timeout)
                covered = backend.covers(pack)
            except (RuntimeError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
                note = f"{backend.name} failed ({type(exc).__name__}); regex fallback used"
        else:
            note = f"{backend.name} not installed; {pack.language} used regex fallback rules"
    rest = RulePack(language=pack.language, extensions=pack.extensions,
                    rules=[r for r in pack.rules if r.id not in covered],
                    sources=pack.sources, sanitizers=pack.sanitizers, linter="regex")
    if rest.rules:
        for path, text in files.items():
            findings += scan_regex(path, text, rest, allow_suppress)
    return findings, note
