"""Loads the rule set the checks read from (prcheck/data/rules.toml by default)."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from importlib import resources
from pathlib import Path


@dataclass(frozen=True)
class SectionRule:
    title: str
    aliases: tuple[str, ...]
    required: bool  # False = recommended (missing is a warning)


@dataclass(frozen=True)
class Rules:
    categories: tuple[str, ...]
    slug_pattern: str
    generic_names: frozenset[str]
    readme_file: str
    max_ai_chars: int
    sections: tuple[SectionRule, ...]
    keep_template_lines: frozenset[str]
    manifests: frozenset[str]
    forbidden_names: frozenset[str]
    forbidden_globs: tuple[str, ...]
    allowed_names: frozenset[str]
    junk_dirs: frozenset[str]
    max_scan_bytes: int
    default_bases: tuple[str, ...]
    max_index_lines_added: int
    max_index_lines_removed: int


def load_rules(path: Path | None = None) -> Rules:
    """Load rules from `path`, or the bundled defaults when no path is given."""
    if path is None:
        raw = resources.files("prcheck").joinpath("data/rules.toml").read_text(encoding="utf-8")
    else:
        raw = path.read_text(encoding="utf-8")
    data = tomllib.loads(raw)

    structure = data["structure"]
    readme = data["readme"]
    files = data["files"]
    scope = data["scope"]
    return Rules(
        categories=tuple(structure["categories"]),
        slug_pattern=structure["slug_pattern"],
        generic_names=frozenset(structure["generic_names"]),
        readme_file=readme["file"],
        max_ai_chars=int(readme["max_ai_chars"]),
        sections=tuple(
            SectionRule(title=s["title"], aliases=tuple(a.lower() for a in s["aliases"]),
                        required=s.get("level", "required") == "required")
            for s in readme["sections"]
        ),
        keep_template_lines=frozenset(" ".join(line.split()) for line in readme.get("keep_template_lines", [])),
        manifests=frozenset(data["dependencies"]["manifests"]),
        forbidden_names=frozenset(files["forbidden_names"]),
        forbidden_globs=tuple(files["forbidden_globs"]),
        allowed_names=frozenset(files["allowed_names"]),
        junk_dirs=frozenset(files["junk_dirs"]),
        max_scan_bytes=int(files["max_scan_bytes"]),
        default_bases=tuple(scope["default_bases"]),
        max_index_lines_added=int(scope["max_index_lines_added"]),
        max_index_lines_removed=int(scope["max_index_lines_removed"]),
    )
