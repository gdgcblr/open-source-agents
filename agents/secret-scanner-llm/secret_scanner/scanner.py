"""Orchestration: file walking -> detectors -> candidates -> (optional) LLM triage."""

from __future__ import annotations

import os
import subprocess
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from . import files as F
from .detectors import find_matches
from .guardrails import confine
from .llm import OllamaClient, OllamaError
from .models import Candidate, Finding
from .redaction import placeholder_hints, redact_line, redact_value
from .triage import triage_all

CONTEXT_RADIUS = 2


@dataclass
class ScanResult:
    findings: list[Finding] = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def incomplete(self) -> bool:
        """True if some files could not be read/processed (a clean result is then not trustworthy)."""
        return bool(self.stats.get("errors"))

    @property
    def exit_code(self) -> int:
        """FAIL CLOSED: 1 if anything non-dismissed exists (incl. unverified); 2 if the scan was
        incomplete and found nothing; else 0."""
        if self.reportable:
            return 1
        return 2 if self.incomplete else 0

    @property
    def reportable(self) -> list[Finding]:
        return [f for f in self.findings if f.reportable]


def scan_text(display_path: str, text: str) -> list[Candidate]:
    """Stage 1 on one file's text. Returned candidates contain only redacted data."""
    lines = text.splitlines()
    redacted_cache: dict[int, str] = {}

    def red(i: int) -> str:
        if i not in redacted_cache:
            redacted_cache[i] = redact_line(lines[i])
        return redacted_cache[i]

    in_test = F.is_test_path(display_path)
    out: list[Candidate] = []
    for i, line in enumerate(lines):
        if F.INLINE_IGNORE in line:
            continue
        for m in find_matches(line):
            if m.rule.keep_whole:
                shown = m.value
            else:
                shown = redact_value(m.value, m.rule.keep)
            lo, hi = max(0, i - CONTEXT_RADIUS), min(len(lines), i + CONTEXT_RADIUS + 1)
            inj = F.looks_like_injection("\n".join(lines[lo:hi]))
            ctx = [f"{'>' if j == i else ' '}{j + 1:5d} | {red(j)}" for j in range(lo, hi)]
            out.append(Candidate(
                file=display_path, line=i + 1, rule=m.rule.name, kind=m.rule.kind,
                redacted_value=shown, context=ctx,
                high_confidence_format=m.rule.high_confidence_format, in_test_path=in_test,
                base_severity=m.rule.severity,
                hints=[] if m.rule.keep_whole else placeholder_hints(m.value),
                injection_suspected=inj,
            ))
    return out


def _read_text(data: bytes) -> str | None:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("utf-8", errors="replace")


def _walk(root: Path, ignore: F.IgnoreRules, stats: Counter):
    if root.is_file():
        yield root, root.name
        return
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = Path(dirpath).relative_to(root).as_posix()
        dirnames[:] = sorted(
            d for d in dirnames
            if d not in F.SKIP_DIRS and not ignore.matches(f"{'' if rel_dir == '.' else rel_dir + '/'}{d}/x")
        )
        for name in sorted(filenames):
            rel = name if rel_dir == "." else f"{rel_dir}/{name}"
            if name == F.IGNORE_FILE:
                continue
            if ignore.matches(rel):
                stats["skipped_ignored"] += 1
                continue
            yield Path(dirpath) / name, rel


def _staged_files(path: Path):
    top = subprocess.run(["git", "-C", str(path), "rev-parse", "--show-toplevel"],
                         capture_output=True, text=True, check=True).stdout.strip()
    names = subprocess.run(
        ["git", "-C", top, "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"],
        capture_output=True, check=True).stdout.decode().split("\0")
    return Path(top), [n for n in names if n]


def collect_candidates(path: str | Path, staged: bool = False) -> tuple[list[Candidate], dict]:
    root = Path(path).expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(f"Path does not exist: {path}")
    stats: Counter = Counter()
    cands: list[Candidate] = []
    errors: list[str] = []

    def handle(name: str, rel: str, data: bytes):
        reason = F.skip_reason(name, len(data), data[:8000])
        if reason:
            stats[f"skipped_{reason}"] += 1
            return
        try:
            found = scan_text(rel, _read_text(data))
        except Exception as e:  # noqa: BLE001 - one bad file must not abort the scan
            stats["errors"] += 1
            stats["skipped_error"] += 1
            errors.append(f"{rel}: {type(e).__name__}")
            return
        stats["files_scanned"] += 1
        cands.extend(found)

    if staged:
        top, names = _staged_files(root if root.is_dir() else root.parent)
        ignore = F.IgnoreRules.load(top)
        for rel in names:
            parts = rel.split("/")
            if set(parts[:-1]) & F.SKIP_DIRS or ignore.matches(rel) or parts[-1] in F.LOCKFILES:
                stats["skipped_ignored"] += 1
                continue
            blob = subprocess.run(["git", "-C", str(top), "show", f":{rel}"], capture_output=True)
            if blob.returncode == 0:
                handle(parts[-1], rel, blob.stdout)
    else:
        base = root if root.is_dir() else root.parent
        ignore = F.IgnoreRules.load(base)
        for fp, rel in _walk(root, ignore, stats):
            if fp.is_symlink():  # never follow links (they could point outside the root)
                stats["skipped_symlink"] += 1
                continue
            try:
                size = fp.stat().st_size
                if size > F.MAX_BYTES:
                    stats["skipped_too_large"] += 1
                    continue
                data = fp.read_bytes()
            except OSError:
                stats["skipped_unreadable"] += 1
                stats["errors"] += 1
                errors.append(f"{rel}: unreadable")
                continue
            handle(fp.name, rel, data)
    out = dict(stats)
    if errors:
        out["error_files"] = errors[:50]
    return cands, out


def scan(path: str | Path, *, use_llm: bool = True, model: str | None = None,
         host: str | None = None, staged: bool = False,
         client: OllamaClient | None = None, progress=None,
         fallback_to_no_llm: bool = True, max_llm_candidates: int | None = 200,
         root: str | Path | None = None) -> ScanResult:
    """Run both stages.

    * `root`: if given, `path` must resolve (symlinks followed) inside it, else PathNotAllowed.
    * If `use_llm` and Ollama is down / the model is missing: with `fallback_to_no_llm` (default)
      the scan continues deterministically with a visible warning; otherwise the error is raised.
      Either way nothing is silently dropped (fail closed).
    """
    t0 = time.perf_counter()
    if root is not None:
        path = confine(path, root)
    warnings: list[str] = []
    owns_client = False
    if use_llm and client is None:
        client = OllamaClient(model=model, host=host)
        owns_client = True
    llm_on = use_llm
    try:
        if llm_on:
            try:
                client.check()
            except OllamaError as e:
                if not fallback_to_no_llm:
                    raise
                llm_on = False
                warnings.append(f"LLM triage unavailable, fell back to --no-llm (all matches reported as "
                                f"unverified): {e}")
        t1 = time.perf_counter()
        cands, stats = collect_candidates(path, staged=staged)
        stage1 = time.perf_counter() - t1
        t2 = time.perf_counter()
        findings = triage_all(cands, client.triage if llm_on else None, progress, warnings,
                              max_llm_candidates if llm_on else None)
        triage_secs = time.perf_counter() - t2
    finally:
        if owns_client and client:
            client.close()
    if stats.get("errors"):
        warnings.append(f"{stats['errors']} file(s) could not be read/processed; the scan is INCOMPLETE.")
    stats.update(
        mode="llm" if llm_on else "no-llm", model=client.model if llm_on else None,
        llm_requested=use_llm, candidates=len(cands), stage1_seconds=round(stage1, 4),
        triage_seconds=round(triage_secs, 3), total_seconds=round(time.perf_counter() - t0, 3),
        llm_requests=client.requests if llm_on else 0, llm_invalid_json=client.invalid_json if llm_on else 0,
        llm_timeouts=client.timeouts if llm_on else 0,
    )
    return ScanResult(findings, stats, warnings)
