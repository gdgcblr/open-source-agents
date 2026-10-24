"""What `run` saves for `apply`, and parsing of `--keep`."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .model import Removal

STATE_FILE = "state.json"
STATE_VERSION = 1
SELECTABLE = ("verified", "unverified")


class StateError(Exception):
    pass


def file_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def number_removals(removals: list[Removal]) -> list[Removal]:
    """Number the removals a developer can select, in file order. Returns them."""
    selectable = [r for r in removals if r.status in SELECTABLE or r.status == "candidate"]
    selectable.sort(key=lambda r: (r.path, r.start, r.key))
    for i, r in enumerate(selectable, 1):
        r.number = i
    return selectable


def save(out_dir: Path, *, root: str, root_arg: str, mode: str, check_mode: str, test_cmd,
         timeout: int, sources: dict[str, str], removals: list[Removal]) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "version": STATE_VERSION, "root": root, "root_arg": root_arg, "mode": mode,
        "check_mode": check_mode, "test_cmd": test_cmd, "timeout": timeout,
        "hashes": {rel: file_hash(text) for rel, text in sources.items()},
        "removals": [r.to_dict() for r in removals],
    }
    path = out_dir / STATE_FILE
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def load(out_dir: Path) -> dict:
    path = out_dir / STATE_FILE
    if not path.exists():
        raise StateError(f"No saved run found at {path}. Run `dead-code-reaper run` first.")
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("version") != STATE_VERSION:
        raise StateError("The saved run was made by a different version. Run again.")
    data["removals"] = [Removal.from_dict(d) for d in data["removals"]]
    return data


def read_sources(root: Path, hashes: dict[str, str]) -> tuple[dict[str, str], list[str]]:
    """Read the files the run saw. Returns (sources, files changed or missing since)."""
    sources, changed = {}, []
    for rel, digest in hashes.items():
        path = root / rel
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            changed.append(rel)
            continue
        if file_hash(text) != digest:
            changed.append(rel)
        sources[rel] = text
    return sources, sorted(changed)


def parse_keep(spec: str | None, removals: list[Removal]) -> set[str]:
    """Turn a --keep value into a set of removal keys.

    Accepts numbers (5), ranges (3-7), file paths (pricing.py), names
    (calculate_tax_v1), and `none`, separated by commas or spaces.
    """
    numbered = {r.number: r for r in removals if r.number}
    if spec is None:
        return {r.key for r in numbered.values() if r.default_keep}
    keys: set[str] = set()
    tokens = [t for t in spec.replace(",", " ").split() if t]
    for tok in tokens:
        if tok.lower() == "none":
            continue
        if tok.isdigit():
            if int(tok) not in numbered:
                raise StateError(f"--keep: there is no removal #{tok}")
            keys.add(numbered[int(tok)].key)
            continue
        if "-" in tok and all(p.isdigit() for p in tok.split("-", 1)):
            a, b = (int(p) for p in tok.split("-", 1))
            missing = [n for n in range(a, b + 1) if n not in numbered]
            if a > b or missing:
                raise StateError(f"--keep: range {tok} is not valid")
            keys.update(numbered[n].key for n in range(a, b + 1))
            continue
        matches = [r for r in numbered.values()
                   if r.path == tok or r.path.endswith("/" + tok) or r.name == tok
                   or r.name.split(".")[-1] == tok]
        if not matches:
            raise StateError(f"--keep: nothing matches '{tok}'")
        keys.update(r.key for r in matches)
    return keys

