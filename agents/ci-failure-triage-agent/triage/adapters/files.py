"""Input adapter: JUnit XML, text logs and history JSON from disk (hardened)."""
import json
from pathlib import Path
from typing import Optional

from defusedxml import ElementTree as ET

from ..models import RunInput, TestFailure

MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_DETAIL_CHARS = 4000


def _read_capped(path: str) -> str:
    p = Path(path)
    if p.stat().st_size > MAX_FILE_BYTES:
        raise ValueError(f"{path} is larger than {MAX_FILE_BYTES // (1024 * 1024)} MB; refusing to parse")
    return p.read_text(encoding="utf-8", errors="replace")


def parse_junit(path: str) -> tuple[list[TestFailure], int]:
    root = ET.fromstring(_read_capped(path))
    failures: list[TestFailure] = []
    total = 0
    for case in root.iter("testcase"):
        total += 1
        rerun = [c for c in case if c.tag in ("flakyFailure", "flakyError", "rerunFailure", "rerunError")]
        fail = next((c for c in case if c.tag in ("failure", "error")), None)
        if fail is None and not rerun:
            continue
        src = fail if fail is not None else rerun[0]
        failures.append(TestFailure(
            name=case.get("name", "unknown"), classname=case.get("classname", ""),
            message=(src.get("message") or "")[:500], details=(src.text or "")[:MAX_DETAIL_CHARS],
            rerun_recorded=bool(rerun), rerun_passed=bool(rerun) and fail is None,
        ))
    return failures, total


def read_log(path: Optional[str]) -> list[str]:
    return _read_capped(path).splitlines() if path else []


def read_history(path: Optional[str]) -> Optional[dict[str, list[str]]]:
    if not path:
        return None
    data = json.loads(_read_capped(path))
    if not isinstance(data, dict) or not all(isinstance(v, list) for v in data.values()):
        raise ValueError('history must be a JSON object like {"test": ["pass", "fail"]}')
    return {str(k): [str(x) for x in v] for k, v in data.items()}


def load_run(junit: str, log: Optional[str] = None, history: Optional[str] = None) -> RunInput:
    failures, total = parse_junit(junit)
    return RunInput(failures=failures, total_tests=total, log_lines=read_log(log), history=read_history(history))
