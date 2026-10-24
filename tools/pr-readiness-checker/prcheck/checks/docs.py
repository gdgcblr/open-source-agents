"""D1-D4: the project README."""

from __future__ import annotations

import re

from .. import markdown
from ..context import ProjectContext
from ..models import Severity
from ..registry import check, finding

GROUP = "docs"

_STOPWORDS = {"and", "the", "how", "to", "of", "for", "with", "your"}
# Bracket placeholders only count outside code blocks (sample output may quote them).
# <project-slug> only counts on a command line inside a code block: a leftover `cd tools/<project-slug>`
# is a real mistake, while prose or sample output that quotes the folder rule (PR #7) is fine.
_PLACEHOLDERS_PROSE = re.compile(r"\[Project Name\]|\[One-sentence summary|\[Language Runtime|\[Package manager"
                                 r"|\[Required API keys")
_PLACEHOLDERS_CODE = re.compile(
    r"^\s*(?:[$>]\s*)?(?:cd|mkdir|cp|mv|copy-item|set-location|ls|dir|python|python3|pip|uv|npm|npx|node|go|"
    r"cargo)\b.*<project-slug>", re.IGNORECASE)
_BARE_NA = re.compile(r"^(n/?a|none|tbd|todo|coming soon)\W*$", re.IGNORECASE)
_MAX_EXAMPLES = 5
UNFILLED_SHARE = 0.5  # share of the template's filler lines still present that makes D3 blocking


@check("D1", group=GROUP, title="README.md exists", severity=Severity.ERROR,
       rule="CONTRIBUTING.md > Step 7; PR checklist 'Documentation'")
def readme_exists(ctx: ProjectContext):
    if ctx.readme_path is None:
        yield finding("D1", f"No {ctx.rules.readme_file} in the project folder; copy template/README.md and fill it in.")
    elif ctx.readme is None:
        yield finding("D1", f"{ctx.readme_path} could not be read as text.", file=ctx.readme_path)


def _matches_rule(heading: str, aliases: tuple[str, ...]) -> bool:
    normalized = markdown.normalize_heading(heading)
    return any(markdown.contains_phrase(normalized, alias) for alias in aliases)


def _significant_tokens(heading: str) -> set[str]:
    return {t for t in markdown.normalize_heading(heading).split() if len(t) >= 4 and t not in _STOPWORDS}


@check("D2", group=GROUP, title="README has the expected sections", severity=Severity.ERROR,
       rule="template/README.md; CONTRIBUTING.md > Step 7")
def readme_sections(ctx: ProjectContext):
    readme = ctx.require_readme()
    headings = [s.title for s in readme.sections]

    missing = [rule for rule in ctx.rules.sections if not any(_matches_rule(h, rule.aliases) for h in headings)]
    missing_required = [rule.title for rule in missing if rule.required]
    missing_recommended = [rule.title for rule in missing if not rule.required]

    # Template headings that no rule covers are still expected, but only warned about,
    # so new template sections are picked up without a code change.
    readme_tokens = set().union(*(_significant_tokens(h) for h in headings)) if headings else set()
    for section in ctx.template.sections:
        if any(_matches_rule(section.title, rule.aliases) for rule in ctx.rules.sections):
            continue
        if not (_significant_tokens(section.title) & readme_tokens):
            missing_recommended.append(section.title)

    if missing_required:
        yield finding("D2", "Missing sections: " + ", ".join(f'"{t}"' for t in missing_required) + ".",
                      file=ctx.readme_path)
    if missing_recommended:
        yield finding("D2", "Template sections not found (add them, or write N/A with a reason): "
                      + ", ".join(f'"{t}"' for t in missing_recommended) + ".",
                      file=ctx.readme_path, severity=Severity.WARN)


def _template_prose(ctx: ProjectContext) -> set[str]:
    lines = set()
    for line, in_code in zip(ctx.template.lines, ctx.template.in_code):
        text = markdown.normalize_line(line)
        if in_code or len(text) < 20 or text.startswith(("#", "|", "---")) or text in ctx.rules.keep_template_lines:
            continue
        lines.add(text)
    return lines


@check("D3", group=GROUP, title="No leftover template text", severity=Severity.WARN,
       rule="CONTRIBUTING.md > Step 7 (fill out all relevant sections)")
def template_leftovers(ctx: ProjectContext):
    readme = ctx.require_readme()
    prose = _template_prose(ctx)
    hits: list[tuple[int, str]] = []
    for number, (line, in_code) in enumerate(zip(readme.lines, readme.in_code), start=1):
        text = markdown.normalize_line(line)
        if in_code:
            leftover = bool(_PLACEHOLDERS_CODE.search(line))
        else:
            leftover = text in prose or bool(_PLACEHOLDERS_PROSE.search(line))
        if leftover:
            hits.append((number, text))
    if hits:
        shown = "; ".join(f'line {n}: "{t[:60]}"' for n, t in hits[:_MAX_EXAMPLES])
        more = f" (+{len(hits) - _MAX_EXAMPLES} more)" if len(hits) > _MAX_EXAMPLES else ""
        # A README that is mostly the untouched template blocks the PR (seen in PR #49).
        unfilled = bool(prose) and len({t for _, t in hits} & prose) >= UNFILLED_SHARE * len(prose)
        prefix = "README is still mostly the template. " if unfilled else ""
        yield finding("D3", f"{prefix}{len(hits)} line(s) still contain template text: {shown}{more}.",
                      file=ctx.readme_path, line=hits[0][0], severity=Severity.ERROR if unfilled else None)


@check("D4", group=GROUP, title="Sections have content (N/A needs a reason)", severity=Severity.WARN,
       rule="CONTRIBUTING.md > Step 7 (N/A with a short explanation)")
def section_content(ctx: ProjectContext):
    readme = ctx.require_readme()
    for section in readme.sections:
        meaningful = [
            line.strip() for line in section.body
            if line.strip() and line.strip() != "---" and not line.lstrip().startswith("#")
        ]
        if not meaningful:
            yield finding("D4", f'Section "{section.title}" is empty.', file=ctx.readme_path, line=section.line)
        elif len(meaningful) == 1 and _BARE_NA.match(meaningful[0].strip("*_ ")):
            yield finding("D4", f'Section "{section.title}" says only "{meaningful[0]}"; add a short reason.',
                          file=ctx.readme_path, line=section.line)
