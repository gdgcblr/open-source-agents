"""Response plans for a newly disclosed RCE in a dependency.

A true zero-day has no vendor fix, so the plan lists the fastest safe responses in order:
(a) upgrade to a fixed version, (b) pin or remove the dependency, (c) a code or config
mitigation at the reachable call sites, (d) a virtual-patch (WAF) idea. Output is a patch
file and notes for human review. Nothing is applied, committed, or pushed.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from pathlib import Path

from rce_sentinel.models import Advisory, Dependency, IntelItem, RiskScore
from rce_sentinel.scanner.deps import normalize_pypi
from rce_sentinel.scanner.reachability import Reach

SAFE_REPLACEMENTS = {
    "yaml.load": "yaml.safe_load",
    "yaml.full_load": "yaml.safe_load",
    "yaml.unsafe_load": "yaml.safe_load",
    "yaml.load_all": "yaml.safe_load_all",
    "yaml.full_load_all": "yaml.safe_load_all",
}
LOADER_KW = re.compile(r",\s*Loader\s*=\s*[\w.]+")

WAF_HINTS = [
    (re.compile(r"yaml", re.I), "Reject request bodies containing `!!python/` YAML tags."),
    (re.compile(r"pickle|deserial", re.I),
     "Reject binary bodies on endpoints that expect JSON; block pickle opcode headers."),
    (re.compile(r"jndi|log4j", re.I), "Block `${jndi:` and nested lookup patterns in headers."),
    (re.compile(r"template|ssti", re.I), "Block `{{` and `{%` in fields that never hold markup."),
    (re.compile(r"command|shell|CWE-78", re.I),
     "Block shell metacharacters (; | ` $( ) in parameters that feed commands."),
]


@dataclass
class Proposal:
    slug: str
    title: str
    options: list[str] = field(default_factory=list)
    patch: str = ""
    advisory_md: str = ""
    pr_md: str = ""


def _diff(path: str, old: str, new: str) -> str:
    return "".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                                        fromfile=f"a/{path}", tofile=f"b/{path}"))


def bump_requirement(text: str, name: str, fixed: str) -> str:
    out = []
    for line in text.splitlines(True):
        m = re.match(r"^(\s*)([A-Za-z0-9][\w.\-]*)(\[[^\]]*\])?\s*==\s*([^\s;#]+)(.*)$",
                     line.rstrip("\n"))
        if m and normalize_pypi(m.group(2)) == name:
            line = f"{m.group(1)}{m.group(2)}{m.group(3) or ''}=={fixed}{m.group(5)}\n"
        out.append(line)
    return "".join(out)


def code_mitigation(text: str, lines: list[int]) -> str:
    src = text.splitlines(True)
    for ln in lines:
        if not 1 <= ln <= len(src):
            continue
        line = src[ln - 1]
        for unsafe, safe in SAFE_REPLACEMENTS.items():
            if f"{unsafe}(" in line:
                line = LOADER_KW.sub("", line.replace(f"{unsafe}(", f"{safe}(", 1))
                break
        src[ln - 1] = line
    return "".join(src)


def build(repo: Path, dep: Dependency, adv: Advisory | None, reach: Reach, item: IntelItem,
          score: RiskScore, verifier_note: str, plan_steps: list[str]) -> Proposal:
    ident = (item.cve_ids or [adv.id if adv else item.content_hash])[0]
    slug = re.sub(r"[^\w.\-]+", "-", f"{ident}-{dep.name}")
    fixed = (adv.fixed_version if adv else None) or item.fixed_version
    options: list[str] = []
    patches: list[str] = []
    if not item.confirmed:
        options.append("No action until an official source confirms this; options below are "
                       "for preparation only.")

    manifest = repo / dep.file
    if fixed:
        options.append(f"(a) Upgrade {dep.name} {dep.version} -> {fixed}.")
        if manifest.exists() and dep.ecosystem == "PyPI" and dep.file.endswith((".txt", ".in")):
            old = manifest.read_text()
            patches.append(_diff(dep.file, old, bump_requirement(old, dep.name, fixed)))
        else:
            options.append(f"    Lockfile {dep.file}: regenerate it with your package manager "
                           f"pinned to {fixed} (command not run by rce-sentinel).")
    elif reach.imported:
        options.append(f"(b) No fixed release yet. Pin {dep.name}=={dep.version} so it cannot "
                       "drift, and apply the mitigation below.")
    else:
        options.append(f"(b) No fixed release, and the repo never imports {dep.name}: remove "
                       f"it from {dep.file}.")

    by_file: dict[str, list[int]] = {}
    for ev in reach.evidence if reach.reachable else []:
        loc = ev.split(" ")[0]
        if ":" in loc:
            path, ln = loc.rsplit(":", 1)
            by_file.setdefault(path, []).append(int(ln))
    for path, lns in sorted(by_file.items()):
        src = repo / path
        if not src.exists():
            continue
        old = src.read_text()
        new = code_mitigation(old, lns)
        if new != old:
            patches.append(_diff(path, old, new))
            options.append(f"(c) Replace the vulnerable call at {path}:{', '.join(map(str, lns))}"
                           " with its safe variant.")
        else:
            options.append(f"(c) Review the call at {path}:{', '.join(map(str, lns))}; add "
                           "input validation or disable the feature.")

    text = f"{item.title} {item.summary} {' '.join(item.cwes)}"
    waf = next((hint for rx, hint in WAF_HINTS if rx.search(text)), None)
    options.append(f"(d) Virtual patch: {waf or 'Add a WAF rule for the affected endpoint.'}")
    options += [f"    model suggestion: {s}" for s in plan_steps[:3]]

    status = "CONFIRMED" if item.confirmed else "UNCONFIRMED (social source only)"
    title = f"Mitigate {ident} in {dep.name} {dep.version}"
    advisory = "\n".join([
        f"# {title}", "",
        f"- Status: {status}; credibility {item.credibility:.2f}; source {item.source}",
        f"- Source link: {item.url}",
        f"- Advisory: {adv.id if adv else 'n/a'} {', '.join(adv.aliases) if adv else ''}",
        f"- Risk: {score.label} ({score.score}); factors {score.factors}",
        f"- Reachable: {reach.reachable}; {'; '.join(reach.evidence)}",
        f"- Cross-family check: {verifier_note}",
        "", "## Response options", *options, "",
        "This is a proposal. Review the patch, then apply it yourself.",
    ])
    pr = "\n".join([
        f"# [draft] {title}", "",
        "## Why", f"{item.title}. {adv.summary if adv else item.summary}", "",
        "## What changes", *[f"- {o.strip()}" for o in options if not o.startswith("    ")], "",
        "## How to apply (manual)",
        "```bash", "git switch -c fix/" + slug, "git apply --check mitigation.patch",
        "git apply mitigation.patch", "# run tests, then open a draft PR yourself:",
        f'gh pr create --draft --title "{title}" --body-file PR_DRAFT.md', "```", "",
        "rce-sentinel generated this draft. It did not commit, push, or open a PR.",
    ])
    return Proposal(slug=slug, title=title, options=options, patch="".join(patches),
                    advisory_md=advisory, pr_md=pr)


def write(proposal: Proposal, out_dir: Path) -> Path:
    d = out_dir / proposal.slug
    d.mkdir(parents=True, exist_ok=True)
    (d / "ADVISORY.md").write_text(proposal.advisory_md, encoding="utf-8")
    (d / "PR_DRAFT.md").write_text(proposal.pr_md, encoding="utf-8")
    (d / "mitigation.patch").write_text(proposal.patch, encoding="utf-8")
    return d
