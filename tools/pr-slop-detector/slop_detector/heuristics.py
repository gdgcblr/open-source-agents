"""Deterministic slop signals. No network, no LLM: fast, free, and explainable.

Each check returns a Signal (or None). Weights are deliberately modest so that no single
signal can flag a PR on its own; the score is the capped sum of weights.
"""

from __future__ import annotations

import json
import re
import sys
import tomllib
from datetime import datetime, timezone
from pathlib import PurePosixPath

from .models import ChangedFile, HeuristicReport, PullRequest, Signal

CODE_EXT = {".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java", ".kt", ".rb", ".c", ".cc", ".cpp", ".h", ".cs", ".swift", ".php"}
DOC_EXT = {".md", ".rst", ".txt", ".adoc"}

# Phrases that show up far more often in LLM-generated prose than in human PR descriptions.
LLM_PHRASES = [
    r"\bdelve[sd]?\b", r"\bcomprehensive\b", r"\brobust\b", r"\bseamless(ly)?\b", r"\bleverag(e|es|ed|ing)\b",
    r"\bstreamlin(e|es|ed|ing)\b", r"\bmeticulous(ly)?\b", r"\belevat(e|es|ing)\b", r"\bfurthermore\b",
    r"\bplays? a (crucial|pivotal|vital) role\b", r"\bit'?s worth noting\b", r"\bin conclusion\b",
    r"\benhanc(e|es|ed|ing) (the )?(overall )?(user experience|maintainability|readability|robustness)\b",
    r"\bensur(e|es|ing) (that )?(the )?(code|application|system) (is|remains)\b", r"\bbest practices\b",
    r"\btestament to\b", r"\bunderscore[sd]?\b", r"\bfoster(s|ing)?\b", r"\bholistic\b", r"\bcutting-edge\b",
    r"\bthis (pr|pull request) (introduces|aims to|adds a comprehensive)\b", r"\bgame[- ]changer\b",
]

# Text a chat assistant produced that was pasted without reading it.
ASSISTANT_LEAKAGE = [
    r"\bas an ai( language model)?\b", r"\bi hope this helps\b", r"\bcertainly!", r"\bhere'?s (the|an?) (updated|revised|improved)\b",
    r"\blet me know if you('d| would)? (like|need|want)\b", r"\bi'?ve (made|implemented) the following changes\b",
    r"\bknowledge cutoff\b", r"\bi (cannot|can't) (browse|access) the internet\b", r"\bgreat question\b",
    r"\bsure[,!] here\b", r"\bbelow is (the|an?) (updated|complete|full)\b",
]

PLACEHOLDERS = [
    r"TODO:? implement", r"#\s*(add|put|insert) your (logic|code|implementation) here", r"//\s*(add|put|insert) your (logic|code) here",
    r"\byour[_-]?api[_-]?key(_here)?\b", r"\.\.\.\s*(rest of|existing) (the )?code", r"#\s*\.\.\.\s*existing code",
    r"\blorem ipsum\b", r"\bplaceholder (implementation|logic)\b", r"raise NotImplementedError",
    r"\bpass\s*#\s*(placeholder|todo|implement)", r"\bmock(ed)? (data|response) for now\b",
]

UNVERIFIED_CLAIMS = [
    r"\ball (the )?tests (pass|passed|are passing)\b", r"\bthoroughly tested\b", r"\bfully tested\b",
    r"\b100% (test )?coverage\b", r"\btested (locally|extensively)\b",
]

# Files that coding assistants love to generate and humans rarely commit.
AI_ARTIFACT_FILES = re.compile(
    r"(^|/)("
    r"[A-Z_]*(IMPLEMENTATION|CHANGES|FIX(ES)?|REFACTOR(ING)?|MIGRATION|UPDATE)S?_?(SUMMARY|NOTES|REPORT|APPLIED|LOG|PLAN|DONE|COMPLETE)\.md"
    r"|[A-Z_]*SUMMARY\.md|PR_DESCRIPTION\.md|NEXT_STEPS\.md|TASKS?_(LIST|DONE)\.md"
    r"|\.aider\.(chat|input)\.history.*|\.cursor/.*|\.windsurf/.*|\.claude/settings\.local\.json"
    r")$",
    re.IGNORECASE,
)

EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿⭐✅❌]")
COMMENT_PREFIX = re.compile(r"^\s*(#|//|/\*|\*|--)\s?(.*)$")
GENERIC_COMMIT = re.compile(r"^(update|add|create|fix|changes?|upload|edit|modify)\s*(files?|[\w./-]+)?\s*(via upload)?\.?$", re.IGNORECASE)
RESTATING_VERBS = re.compile(
    r"^(import|initiali[sz]e|define|create|set|get|return|call|increment|decrement|loop (over|through)|iterate|check if|print|declare|assign|add) ",
    re.IGNORECASE,
)

# Import name -> distribution name, for the most common mismatches.
IMPORT_ALIASES = {
    "yaml": "pyyaml", "cv2": "opencv-python", "pil": "pillow", "sklearn": "scikit-learn", "bs4": "beautifulsoup4",
    "dotenv": "python-dotenv", "dateutil": "python-dateutil", "jwt": "pyjwt", "google": "google-*", "attr": "attrs",
    "magic": "python-magic", "serial": "pyserial", "crypto": "pycryptodome", "telegram": "python-telegram-bot",
    "docx": "python-docx", "pptx": "python-pptx", "git": "gitpython", "multipart": "python-multipart",
}


# ------------------------------------------------------------------ helpers


def added_lines(f: ChangedFile) -> list[tuple[int, str]]:
    """(new-file line number, text) for every added line in the patch."""
    out, lineno = [], 0
    for line in (f.patch or "").splitlines():
        if line.startswith("@@"):
            m = re.search(r"\+(\d+)", line)
            lineno = int(m.group(1)) if m else 0
        elif line.startswith("+") and not line.startswith("+++"):
            out.append((lineno, line[1:]))
            lineno += 1
        elif not line.startswith("-"):
            lineno += 1
    return out


def _ext(name: str) -> str:
    return PurePosixPath(name).suffix.lower()


def _find(patterns: list[str], text: str) -> list[str]:
    hits = []
    for p in patterns:
        for m in re.finditer(p, text, re.IGNORECASE):
            hits.append(m.group(0))
    return hits


def _snip(s: str, n: int = 90) -> str:
    s = s.strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def _words(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", s.lower()) if len(w) > 2}


def _split_ident(s: str) -> set[str]:
    s = re.sub(r"([a-z])([A-Z])", r"\1 \2", s)
    return _words(s.replace("_", " "))


# ------------------------------------------------------------------ description checks


def check_llm_phrasing(pr: PullRequest) -> Signal | None:
    text = f"{pr.title}\n{pr.body}"
    hits = _find(LLM_PHRASES, text)
    words = max(len(text.split()), 1)
    density = len(hits) / words * 100  # hits per 100 words
    if len(hits) < 3 or density < 1.0:
        return None
    weight = min(20, 5 + len(hits) * 2)
    uniq = sorted({h.lower() for h in hits})
    return Signal(
        id="llm-phrasing", category="description", title="Description is dense with stock LLM phrasing", weight=weight,
        evidence=[f"{len(hits)} hits in {words} words ({density:.1f}/100 words): " + ", ".join(f'"{u}"' for u in uniq[:8])],
    )


def check_assistant_leakage(pr: PullRequest) -> Signal | None:
    sources = [("PR description", f"{pr.title}\n{pr.body}")]
    sources += [("commit message", m) for m in pr.commit_messages]
    sources += [(f.filename, "\n".join(t for _, t in added_lines(f))) for f in pr.files]
    ev = [f'{where}: "{h}"' for where, text in sources for h in _find(ASSISTANT_LEAKAGE, text)]
    if not ev:
        return None
    return Signal(
        id="assistant-leakage", category="description", title="Chat-assistant text pasted verbatim", weight=min(30, 18 + 4 * len(ev)),
        evidence=ev[:5],
    )


def check_emoji_structure(pr: PullRequest) -> Signal | None:
    headings = [l for l in pr.body.splitlines() if re.match(r"^\s*(#{1,6}\s|\*\*)", l)]
    emoji_headings = [h for h in headings if EMOJI.search(h)]
    if len(emoji_headings) < 2:
        return None
    return Signal(
        id="emoji-headings", category="description", title="Emoji-decorated section headings", weight=6,
        evidence=[_snip(h) for h in emoji_headings[:4]],
    )


def check_description_vs_diff(pr: PullRequest) -> Signal | None:
    body_words = len(pr.body.split())
    changed = pr.additions + pr.deletions
    if body_words < 150 or changed == 0 or body_words / changed < 4:
        return None
    return Signal(
        id="description-inflation", category="description", title="Description is far larger than the change", weight=8,
        evidence=[f"{body_words} words of description for {changed} changed lines"],
    )


def check_unverified_claims(pr: PullRequest) -> Signal | None:
    claims = _find(UNVERIFIED_CLAIMS, pr.body)
    if not claims:
        return None
    has_tests = any(re.search(r"(^|/)(tests?|__tests__|spec)(/|_)|_test\.|\.test\.|\.spec\.|test_", f.filename) for f in pr.files)
    if has_tests:
        return None
    return Signal(
        id="unverified-claims", category="description", title="Claims testing that the diff does not show", weight=10,
        evidence=[", ".join(f'"{c}"' for c in sorted(set(claims))[:4]) + ", yet no test files were added or changed"],
    )


# ------------------------------------------------------------------ diff checks


def check_comments(pr: PullRequest) -> list[Signal]:
    restating: list[str] = []
    total_comments = total_code = 0
    for f in pr.files:
        if _ext(f.filename) not in CODE_EXT:
            continue
        lines = added_lines(f)
        for i, (lineno, text) in enumerate(lines):
            m = COMMENT_PREFIX.match(text)
            if not m:
                if text.strip():
                    total_code += 1
                continue
            total_comments += 1
            comment = m.group(2).strip()
            nxt = next((t for _, t in lines[i + 1 :] if t.strip() and not COMMENT_PREFIX.match(t)), "")
            overlap = _words(comment) & _split_ident(nxt)
            if comment and nxt and (RESTATING_VERBS.match(comment) and (overlap or len(comment.split()) <= 4)):
                restating.append(f"{f.filename}:{lineno} `{_snip(comment, 50)}` → `{_snip(nxt, 50)}`")
    out = []
    if len(restating) >= 3:
        out.append(Signal(
            id="restating-comments", category="diff", title="Comments that restate the next line of code",
            weight=min(15, 4 + 2 * len(restating)), evidence=restating[:5],
        ))
    if total_code >= 30 and total_comments / total_code > 0.45:
        out.append(Signal(
            id="comment-density", category="diff", title="Unusually high comment-to-code ratio", weight=6,
            evidence=[f"{total_comments} comment lines for {total_code} code lines ({total_comments / total_code:.0%})"],
        ))
    return out


def check_placeholders(pr: PullRequest) -> Signal | None:
    ev = []
    for f in pr.files:
        if f.filename.endswith(".env.example") or _ext(f.filename) in DOC_EXT:
            continue  # placeholders are expected in templates and docs
        for lineno, text in added_lines(f):
            for h in _find(PLACEHOLDERS, text):
                ev.append(f"{f.filename}:{lineno} `{_snip(h, 60)}`")
    if not ev:
        return None
    return Signal(
        id="placeholder-code", category="diff", title="Placeholder or unfinished code", weight=min(18, 6 + 3 * len(ev)), evidence=ev[:5],
    )


def check_ai_artifact_files(pr: PullRequest) -> Signal | None:
    hits = [f.filename for f in pr.files if f.status != "removed" and AI_ARTIFACT_FILES.search(f.filename)]
    if not hits:
        return None
    return Signal(
        id="ai-artifact-files", category="diff", title="Committed assistant scratch files", weight=min(15, 8 + 3 * len(hits)), evidence=hits[:5],
    )


def check_whitespace_churn(pr: PullRequest) -> Signal | None:
    churn = []
    for f in pr.files:
        if not f.patch:
            continue
        adds = sorted(re.sub(r"\s+", "", l[1:]) for l in f.patch.splitlines() if l.startswith("+") and not l.startswith("+++"))
        dels = sorted(re.sub(r"\s+", "", l[1:]) for l in f.patch.splitlines() if l.startswith("-") and not l.startswith("---"))
        if adds and adds == dels:
            churn.append(f.filename)
    if len(churn) < 2:
        return None
    return Signal(
        id="whitespace-churn", category="diff", title="Files with whitespace/formatting-only changes", weight=min(12, 3 * len(churn)),
        evidence=churn[:6],
    )


def check_scope_sprawl(pr: PullRequest) -> Signal | None:
    tops = {PurePosixPath(f.filename).parts[0] if len(PurePosixPath(f.filename).parts) > 1 else "(root)" for f in pr.files}
    if len(pr.files) < 15 or len(tops) < 5:
        return None
    return Signal(
        id="scope-sprawl", category="diff", title="Change sprawls across many unrelated areas", weight=8,
        evidence=[f"{len(pr.files)} files across {len(tops)} top-level directories: {', '.join(sorted(tops)[:8])}"],
    )


def check_broad_excepts(pr: PullRequest) -> Signal | None:
    ev = []
    for f in pr.files:
        if _ext(f.filename) not in {".py", ".js", ".ts", ".tsx", ".jsx"}:
            continue
        for lineno, text in added_lines(f):
            if re.match(r"\s*except(\s+(Base)?Exception)?(\s+as\s+\w+)?\s*:", text) or re.match(r"\s*\}\s*catch\s*(\(\w*\))?\s*\{\s*\}?", text):
                ev.append(f"{f.filename}:{lineno} `{_snip(text, 50)}`")
    if len(ev) < 4:
        return None
    return Signal(
        id="blanket-error-handling", category="diff", title="Blanket try/except wrapped around everything", weight=min(10, 2 + len(ev)),
        evidence=ev[:5],
    )


def _declared_python_deps(manifests: dict[str, str]) -> set[str]:
    deps: set[str] = set()
    for path, text in manifests.items():
        name = PurePosixPath(path).name
        if name == "requirements.txt":
            for line in text.splitlines():
                line = line.split("#")[0].strip()
                if line and not line.startswith("-"):
                    deps.add(re.split(r"[\s<>=!~;\[]", line, maxsplit=1)[0].lower())
        elif name == "pyproject.toml":
            try:
                data = tomllib.loads(text)
            except tomllib.TOMLDecodeError:
                continue
            reqs = list(data.get("project", {}).get("dependencies", []))
            for group in data.get("project", {}).get("optional-dependencies", {}).values():
                reqs += group
            reqs += list(data.get("tool", {}).get("poetry", {}).get("dependencies", {}).keys())
            deps |= {re.split(r"[\s<>=!~;\[]", r, maxsplit=1)[0].lower() for r in reqs}
    return {d.replace("_", "-") for d in deps if d}


def _declared_js_deps(manifests: dict[str, str]) -> set[str]:
    deps: set[str] = set()
    for path, text in manifests.items():
        if PurePosixPath(path).name != "package.json":
            continue
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            continue
        for key in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
            deps |= set(data.get(key, {}).keys())
    return deps


def check_undeclared_imports(pr: PullRequest) -> Signal | None:
    """Imports of third-party packages that no manifest declares: hallucinated or forgotten dependencies."""
    manifests = dict(pr.manifests)
    for f in pr.files:  # manifests changed in the PR count too
        if PurePosixPath(f.filename).name in {"requirements.txt", "pyproject.toml", "package.json"} and f.patch:
            manifests[f.filename] = manifests.get(f.filename, "") + "\n" + "\n".join(t for _, t in added_lines(f))
    py_deps, js_deps = _declared_python_deps(manifests), _declared_js_deps(manifests)
    has_py_manifest = any(PurePosixPath(p).name in {"requirements.txt", "pyproject.toml"} for p in manifests)
    has_js_manifest = any(PurePosixPath(p).name == "package.json" for p in manifests)

    # Local modules: anything in the repo tree, plus files/directories the PR adds.
    local = {m.lower() for m in pr.local_modules}
    for f in pr.files:
        for part in PurePosixPath(f.filename).parts:
            local.add(PurePosixPath(part).stem.lower())

    ev = []
    for f in pr.files:
        ext = _ext(f.filename)
        for lineno, text in added_lines(f):
            if ext == ".py" and has_py_manifest:
                m = re.match(r"\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))", text)
                if not m:
                    continue
                mod = (m.group(1) or m.group(2)).split(".")[0]
                if not mod or mod.startswith("_") or mod in sys.stdlib_module_names or mod.lower() in local:
                    continue
                dist = IMPORT_ALIASES.get(mod.lower(), mod.lower()).replace("_", "-")
                ok = dist in py_deps or (dist.endswith("*") and any(d.startswith(dist[:-1]) for d in py_deps))
                if not ok:
                    ev.append(f"{f.filename}:{lineno} imports `{mod}`, not declared in any manifest")
            elif ext in {".js", ".jsx", ".ts", ".tsx", ".mjs"} and has_js_manifest:
                m = re.search(r"""(?:from\s+|require\(\s*|import\s+)['"]([^'"]+)['"]""", text)
                if not m or m.group(1).startswith((".", "/", "node:", "@/", "~")):
                    continue
                spec = m.group(1)
                pkg = "/".join(spec.split("/")[:2]) if spec.startswith("@") else spec.split("/")[0]
                if pkg not in js_deps:
                    ev.append(f"{f.filename}:{lineno} imports `{pkg}`, not declared in package.json")
    if not ev:
        return None
    return Signal(
        id="undeclared-imports", category="diff", title="Imports packages no manifest declares (hallucinated or missing deps)",
        weight=min(18, 8 + 3 * len(ev)), evidence=ev[:5],
    )


# ------------------------------------------------------------------ context checks


def check_commits(pr: PullRequest) -> Signal | None:
    if not pr.commit_messages:
        return None
    generic = [m.splitlines()[0] for m in pr.commit_messages if GENERIC_COMMIT.match(m.splitlines()[0].strip())]
    big = pr.additions >= 300
    if len(pr.commit_messages) == 1 and big and generic:
        return Signal(
            id="single-dump-commit", category="context", title="Large change dumped in one generically named commit", weight=7,
            evidence=[f'1 commit "{_snip(generic[0], 60)}" adding {pr.additions} lines'],
        )
    if len(generic) >= 3 and len(generic) / len(pr.commit_messages) >= 0.8:
        return Signal(
            id="generic-commits", category="context", title="Commit messages are uninformative", weight=4,
            evidence=[f'{len(generic)}/{len(pr.commit_messages)} commits like "{_snip(generic[0], 40)}"'],
        )
    return None


def check_author(pr: PullRequest, now: datetime | None = None) -> list[Signal]:
    now = now or datetime.now(timezone.utc)
    a, out = pr.author, []
    if a.account_created_at:
        age = (now - datetime.fromisoformat(a.account_created_at.replace("Z", "+00:00"))).days
        if age < 30 and a.association in {"NONE", "FIRST_TIME_CONTRIBUTOR", "FIRST_TIMER"}:
            out.append(Signal(
                id="new-account", category="context", title="Brand-new account, first contribution", weight=5,
                evidence=[f"@{a.login} created {age} days ago, association {a.association}"],
            ))
    if a.recent_pr_count is not None and a.recent_pr_count >= 15 and (a.recent_pr_repo_count or 0) >= 8:
        out.append(Signal(
            id="pr-spray", category="context", title="Author is spraying PRs across many repositories", weight=12,
            evidence=[f"@{a.login} opened {a.recent_pr_count} PRs across ≥{a.recent_pr_repo_count} repos recently"],
        ))
    return out


def run_heuristics(pr: PullRequest, now: datetime | None = None) -> HeuristicReport:
    # Bots (dependabot, renovate, ...) write templated descriptions and open PRs everywhere by design.
    is_bot = pr.author.login.endswith("[bot]")
    checks = [
        check_llm_phrasing, check_assistant_leakage, check_emoji_structure, check_description_vs_diff,
        check_unverified_claims, check_placeholders, check_ai_artifact_files, check_whitespace_churn,
        check_scope_sprawl, check_broad_excepts, check_undeclared_imports, check_commits,
    ]
    if is_bot:
        checks = [c for c in checks if c not in (check_description_vs_diff, check_emoji_structure, check_commits)]
    signals: list[Signal] = [s for check in checks if (s := check(pr))]
    signals += check_comments(pr)
    if not is_bot:
        signals += check_author(pr, now)
    signals.sort(key=lambda s: s.weight, reverse=True)
    return HeuristicReport(score=min(100, sum(s.weight for s in signals)), signals=signals)
