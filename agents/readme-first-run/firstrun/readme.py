"""Reading a README the way a newcomer would: find the commands, in order."""

from __future__ import annotations

import re
import shlex
from pathlib import Path
from typing import Optional

from .models import Plan, Skipped, Step
from .project import find_readme, read_text

COMMAND_LANGS = {
    "bash", "sh", "shell", "zsh", "console", "terminal", "shell-session",
    "shellsession", "sh-session", "cmd-line", "commandline",
}
# Blocks in these languages are code or output, never something to type into a terminal.
IGNORED_LANGS = {
    "python", "py", "python3", "pycon", "json", "jsonc", "yaml", "yml", "toml", "ini", "cfg",
    "env", "dotenv", "text", "txt", "plaintext", "output", "log", "diff", "javascript", "js",
    "typescript", "ts", "html", "css", "sql", "xml", "markdown", "md", "mermaid", "powershell",
    "ps1", "pwsh", "bat", "cmd", "batch", "dockerfile", "go", "rust", "java", "c", "cpp",
}
KNOWN_COMMANDS = {
    "pip", "pip3", "python", "python3", "py", "uv", "uvx", "poetry", "pipenv", "pdm", "hatch",
    "pipx", "conda", "cp", "mv", "mkdir", "export", "source", ".", "cd", "npm", "npx", "node",
    "yarn", "pnpm", "make", "streamlit", "uvicorn", "adk", "pytest", "bash", "sh", "chmod",
    "touch", "docker", "docker-compose", "flask", "gunicorn", "git", "echo", "cat", "curl",
    "wget", "tox", "nox", "jupyter", "gradio", "chainlit", "fastapi", "mkdocs", "deactivate",
}
PACKAGE_MANAGERS = {
    "uv": "pip install uv", "poetry": "pip install poetry", "pipenv": "pip install pipenv",
    "pdm": "pip install pdm", "hatch": "pip install hatch", "pipx": "pip install pipx",
    "tox": "pip install tox", "nox": "pip install nox",
}

FENCE_RE = re.compile(r"^(\s*)(`{3,}|~{3,})\s*(.*)$")
HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
SETEXT_RE = re.compile(r"^\s{0,3}(=+|-+)\s*$")
PROMPT_RE = re.compile(r"^\s*(?:\(\.?venv\)\s*)?\$\s?(.*)$")
STRAY_PROMPT_RE = re.compile(r"^(?:\$|%|>>>?)\s+")
SECRET_NAME_RE = re.compile(
    r"\b((?:[A-Z][A-Z0-9]*_)+(?:API_KEY|KEY|TOKEN|SECRET|PASSWORD)|API_KEY)\b"
)
PLACEHOLDER_RE = re.compile(r"<[^>]+>|your[_-]|_here\b|xxx|changeme|\.\.\.", re.I)
# Arguments a reader is meant to replace with their own input. Real example values such as
# example.com URLs are fine and are left alone.
ARG_PLACEHOLDER_RE = re.compile(
    r"(?:^|[=/])path/to/|^/path/|<[^<>\s][^<>]*>|(?i:\byour[_-]\w+)|\bYOUR_[A-Z0-9_]+"
    r"|(?i:_here\b)|(?<![A-Za-z])(?:OWNER|REPO|USERNAME)(?![A-Za-z])|(?i:\bchangeme\b)"
    # example repos and URLs: owner/repo, owner/repository/pull/42, your-org, example.com inputs
    r"|(?i:(?:^|[/:=])(?:owner|user|username|org|your-org|your_org|my-org)/"
    r"(?:repo|repository|project|your-repo|your_repo|my-repo)(?:[/.#?]|$))"
    r"|(?i:\bhttps?://(?:www\.)?example\.(?:com|org|net)\b)"
)
# commands that set things up; placeholders there keep their own handling (notes, cd skips)
SETUP_WORDS = {
    "pip", "pip3", "cp", "mv", "export", "source", ".", "cd", "mkdir", "git", "uv", "poetry",
    "pipenv", "pdm", "conda", "touch", "chmod", "echo", "cat", "set", "deactivate", "curl", "wget",
}

LONG_RUNNING_RE = re.compile(
    r"\bstreamlit\s+run\b|\buvicorn\b|\bflask\s+run\b|\bgunicorn\b|\badk\s+(?:web|api_server)\b"
    r"|\bpython3?\s+-m\s+(?:http\.server|uvicorn|streamlit\s+run|flask\s+run)"
    r"|\b(?:npm|pnpm)\s+(?:start|run\s+(?:dev|start|serve))\b|\byarn\s+(?:start|dev)\b"
    r"|\bgradio\s+\S+|\bjupyter\s+(?:notebook|lab)\b|\bdocker(?:-|\s+)compose\s+up\b(?!.*\s-d\b)"
    r"|\bchainlit\s+run\b|\bmkdocs\s+serve\b|\bfastapi\s+(?:dev|run)\b|\blanggraph\s+dev\b"
    r"|\bpython3?\s+-m\s+[\w.]+\.(?:web|server|serve|app)\b|\brunserver\b|\b(?:hugo|jekyll)\s+serve\b"
)
# Authors can steer FirstRun from the README itself, on the line right before a code block:
#   <!-- firstrun: skip needs a GitHub login -->     <!-- firstrun: long-running -->
#   <!-- firstrun: expect-exit 1 -->   (a linter demo that is supposed to report problems)
DIRECTIVE_RE = re.compile(r"^\s*<!--\s*firstrun:\s*(skip|long-running|expect-exit)\b\s*(.*?)\s*-->\s*$", re.I)
SERVER_CODE_RE = re.compile(
    r"\b(?:uvicorn\.run|app\.run|serve_forever|run_app|run_server|socketio\.run)\s*\("
)

WINDOWS_RE = re.compile(
    r"\\Scripts\\|\.ps1\b|\bCopy-Item\b|\bRemove-Item\b|\$env:|^set\s+\w+=|^setx\s|"
    r"\b\.?venv\\|^copy\s|^py\s+-\d|^py\s+-m\s|\.bat\b|\.cmd\b|^dir\b|^cls$",
    re.I,
)


def _lang_of(info: str) -> str:
    first = info.strip().split(None, 1)[0] if info.strip() else ""
    return first.strip("{}.").lower()


def parse_code_blocks(text: str) -> list[dict]:
    """Fenced code blocks with their language, starting line and the heading above them.

    Each block also has "lines" (list of (line_number, dedented text)), "start" and "end"
    (the fence lines) and "section_index" (which heading it belongs to).
    """
    blocks: list[dict] = []
    lines = text.splitlines()
    section, section_index = "", 0
    i = 0
    prev_nonblank = ""
    while i < len(lines):
        raw = lines[i]
        fence = FENCE_RE.match(raw)
        if fence:
            indent, marker, info = fence.groups()
            ch, size = marker[0], len(marker)
            body: list[tuple[int, str]] = []
            j = i + 1
            closed = False
            while j < len(lines):
                close = re.match(r"^\s*(" + re.escape(ch) + r"{" + str(size) + r",})\s*$", lines[j])
                if close:
                    closed = True
                    break
                line = lines[j]
                # strip the fence's own indentation (blocks nested in list items)
                strip = min(len(indent), len(line) - len(line.lstrip()))
                body.append((j + 1, line[strip:]))
                j += 1
            directive = None
            k = i - 1
            while k >= 0 and not lines[k].strip():
                k -= 1
            if k >= 0:
                d = DIRECTIVE_RE.match(lines[k])
                if d:
                    directive = (d.group(1).lower(), d.group(2).strip())
            blocks.append({
                "directive": directive,
                "lang": _lang_of(info),
                "code": "\n".join(t for _, t in body),
                "line": i + 2,
                "start": i + 1,
                "end": j + 1 if closed else len(lines),
                "section": section,
                "section_index": section_index,
                "lines": body,
            })
            i = j + 1
            prev_nonblank = ""
            continue
        heading = HEADING_RE.match(raw)
        if heading:
            section = heading.group(2).strip()
            section_index += 1
        elif SETEXT_RE.match(raw) and prev_nonblank and not prev_nonblank.lstrip().startswith(("-", "*", "|", ">")):
            # "Title\n=====" style heading. A "---" after a blank line is just a rule.
            section = prev_nonblank.strip()
            section_index += 1
        if raw.strip():
            prev_nonblank = raw
        else:
            prev_nonblank = ""
        i += 1
    return blocks


def strip_comment(line: str) -> str:
    """Drop a trailing `# comment`, leaving # inside quotes alone."""
    quote = None
    prev = " "
    for idx, ch in enumerate(line):
        if quote:
            if ch == quote and line[idx - 1] != "\\":
                quote = None
        elif ch in "'\"":
            quote = ch
        elif ch == "#" and prev.isspace():
            return line[:idx].rstrip()
        prev = ch
    return line.rstrip()


def command_word(command: str) -> str:
    """The program a command runs, skipping env assignments and sudo."""
    first_line = command.strip().splitlines()[0] if command.strip() else ""
    try:
        words = shlex.split(first_line, comments=False)
    except ValueError:
        words = first_line.split()
    for w in words:
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", w):
            continue
        if w in ("sudo", "env", "time", "exec"):
            continue
        return w
    return ""


def _os_context(comment: str, current: Optional[str]) -> Optional[str]:
    c = comment.lower()
    has_win = bool(re.search(r"windows|powershell|\bcmd\b|command prompt", c))
    has_unix = bool(re.search(r"\b(?:linux|unix|bash|zsh|wsl|ubuntu|debian)\b", c))
    has_mac = bool(re.search(r"\bmac(?:os)?\b|\bos\s?x\b|\bdarwin\b|\bhomebrew\b", c))
    if has_win and not (has_unix or has_mac):
        return "windows"
    if has_mac and not (has_unix or has_win):
        return "macos"
    if has_unix or has_mac or has_win:
        return None
    return current


def _section_os(section: str) -> Optional[str]:
    return _os_context(section, None)


def _block_commands(block: dict) -> list[dict]:
    """Commands inside one block: {"line", "command", "os"}."""
    lang = block["lang"]
    if lang in IGNORED_LANGS:
        return []
    if lang and lang not in COMMAND_LANGS:
        return []
    neutral = lang == ""
    lines = block["lines"]
    has_prompt = any(PROMPT_RE.match(t) and t.strip().startswith(("$", "(")) for _, t in lines)
    out = []
    os_ctx = _section_os(block["section"])
    i = 0
    while i < len(lines):
        ln, raw = lines[i]
        s = raw.strip()
        if not s:
            os_ctx = _section_os(block["section"])
            i += 1
            continue
        if has_prompt:
            m = PROMPT_RE.match(raw)
            if not m or not raw.strip().startswith(("$", "(")):
                i += 1  # output line in a console transcript
                continue
            s = m.group(1).strip()
        else:
            s = STRAY_PROMPT_RE.sub("", s)
        if s.startswith("#"):
            os_ctx = _os_context(s, os_ctx)
            i += 1
            continue
        parts = [strip_comment(s)]
        while parts[-1].endswith("\\") and i + 1 < len(lines):
            i += 1
            nxt = lines[i][1].strip()
            if has_prompt:
                nxt = re.sub(r"^>\s*", "", nxt)
            parts.append(strip_comment(nxt))
        command = "\n".join(parts).strip()
        heredoc = re.search(r"<<-?\s*['\"]?(\w+)['\"]?", command)
        if heredoc:
            delim = heredoc.group(1)
            body = []
            while i + 1 < len(lines):
                i += 1
                body.append(lines[i][1])
                if lines[i][1].strip() == delim:
                    break
            command = command + "\n" + "\n".join(body)
        i += 1
        if not command:
            continue
        if neutral and command_word(command) not in KNOWN_COMMANDS and not command.startswith("./"):
            continue
        out.append({"line": ln, "command": command, "os": os_ctx})
    return out


def _kind(command: str, word: str, section: str) -> str:
    c, s = command.lower(), section.lower()
    if "prereq" in s:
        return "prerequisite"
    if re.search(r"\bpytest\b|\bunittest\b|\btox\b|\bnox\b|\bmake\s+test\b", c):
        return "test"
    if word in ("cp", "mv", "export", "echo", "cat", "touch") and re.search(r"\.env\b|\bexport\s+\w+=", c):
        return "configure"
    if word == "export":
        return "configure"
    if re.search(
        r"\b(?:pip3?|uv|poetry|pipenv|conda|pdm|npm|yarn|pnpm)\b.*\b(?:install|sync|add|create|ci)\b"
        r"|\bvenv\b|virtualenv|\bactivate\b",
        c,
    ):
        return "setup"
    if word in ("python", "python3", "streamlit", "uvicorn", "flask", "adk", "node", "gunicorn",
                "npm", "yarn", "pnpm", "make", "docker", "gradio", "chainlit", "jupyter") or c.startswith("./"):
        return "run"
    if any(k in s for k in ("test",)):
        return "test"
    if any(k in s for k in ("config", "environment", "env var", "api key", "credential", "secret")):
        return "configure"
    if any(k in s for k in ("install", "setup", "set up", "getting started")):
        return "setup"
    return "run"


def _long_running(command: str, project_dir: Path) -> bool:
    if LONG_RUNNING_RE.search(command):
        return True
    m = re.search(r"\bpython3?\s+((?:[\w./-]+/)?[\w.-]+\.py)\b", command)
    if m:
        text = read_text(project_dir / m.group(1), limit=100_000) or ""
        if SERVER_CODE_RE.search(text):
            return True
        if re.search(r"^\s*(?:import|from)\s+gradio\b", text, re.M) and ".launch(" in text:
            return True
    return False


def _cd_target(command: str) -> Optional[tuple[str, str]]:
    """For `cd X` or `cd X && rest`, return (X, rest)."""
    m = re.match(r"^cd\s+(\"[^\"]+\"|'[^']+'|\S+)\s*(?:(?:&&|;)\s*(.*))?$", command.strip(), re.S)
    if not m:
        return None
    return m.group(1).strip("\"'"), (m.group(2) or "").strip()


def _skip_cd(target: str, project_dir: Path, clone_dirs: set[str], created: set[str]) -> Optional[str]:
    t = target.rstrip("/")
    if re.search(r"[<>{}\[\]]", t) or "your-" in t.lower() or "your_" in t.lower():
        return "cd into a placeholder path (FirstRun already starts in the project folder)"
    if t in clone_dirs or t.split("/")[0] in clone_dirs:
        return "cd into the cloned repo (project is already the working directory)"
    if re.match(r"^(?:\./)?(?:agents|tools)/", t) or "/agents/" in t or "/tools/" in t:
        return "cd into the project folder (FirstRun already starts there)"
    if t and t.split("/")[-1] == project_dir.name and not (project_dir / t).is_dir():
        return "cd into the project folder (FirstRun already starts there)"
    if t in ("..", "-", "~", "") or t.startswith(("..", "~", "/", "$")):
        return None
    if not (project_dir / t).exists() and t.split("/")[0] not in created:
        return "cd into a folder that is not in the project (assumed to be the project root)"
    return None


def _secret_envs(project_dir: Path, readme_text: str) -> list[str]:
    names: list[str] = []
    example = read_text(project_dir / ".env.example") or ""
    for line in example.splitlines():
        m = re.match(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", line)
        if not m:
            continue
        name, value = m.group(1), m.group(2).strip().strip("\"'")
        secretish = bool(re.search(r"KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL", name, re.I))
        if secretish or not value or PLACEHOLDER_RE.search(value):
            if name not in names:
                names.append(name)
    for m in SECRET_NAME_RE.finditer(readme_text):
        if m.group(1) not in names:
            names.append(m.group(1))
    return names


def _prereq_prose(text: str) -> str:
    """Prose (outside code blocks) under Prerequisites / Requirements headings."""
    out, keep, in_fence = [], False, False
    for line in text.splitlines():
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        h = HEADING_RE.match(line)
        if h and not in_fence:
            keep = bool(re.search(r"prereq|requirement|before you (?:begin|start)|you(?:'ll| will) need", h.group(2), re.I))
            continue
        if keep and not in_fence:
            out.append(line)
    return "\n".join(out)


def _expected_output(blocks: list[dict]) -> Optional[str]:
    seen_sections = set()
    for b in blocks:
        first_in_section = b["section_index"] not in seen_sections
        seen_sections.add(b["section_index"])
        if first_in_section and re.search(r"\boutput\b", b["section"], re.I) and b["code"].strip():
            return b["code"]
    return None


def directives(readme_text: str) -> dict[int, tuple[str, str]]:
    """README line -> (directive, note) for every line inside an annotated code block."""
    out = {}
    for b in parse_code_blocks(readme_text):
        if b.get("directive"):
            for line_no, _ in b["lines"]:
                out[line_no] = b["directive"]
    return out


def run_placeholder(step: Step) -> Optional[str]:
    """The placeholder argument in a run command (`path/to/your/file.pdf`), if it has one."""
    word = command_word(step.command)
    if word in SETUP_WORDS:
        return None
    if re.search(r"\s-m\s+(?:pip|venv)\b", step.command):
        return None
    if step.kind not in ("run", "test") and word not in ("python", "python3", "py"):
        return None
    try:
        tokens = shlex.split(step.command.replace("\\\n", " "))
    except ValueError:
        tokens = step.command.split()
    for token in tokens[1:]:
        if ARG_PLACEHOLDER_RE.search(token):
            return token
    return None


def _skip(plan: Plan, step: Step, reason: str) -> None:
    if not any(k.line == step.line and k.command == step.command for k in plan.skipped):
        plan.skipped.append(Skipped(step.command, reason, step.line))


def apply_directives(plan: Plan, readme_text: str) -> Plan:
    """Re-apply README annotations and placeholder skips, so an AI planner cannot undo them."""
    marks = directives(readme_text)
    kept = []
    for step in plan.steps:
        mark = marks.get(step.line) if step.line else None
        if mark and mark[0] == "skip":
            _skip(plan, step, "marked `firstrun: skip` in the README" + (f" ({mark[1]})" if mark[1] else ""))
            continue
        placeholder = None if step.provided_by_firstrun else run_placeholder(step)
        if placeholder:
            _skip(plan, step, f"needs your own input (placeholder `{placeholder}`)")
            continue
        if mark and mark[0] == "long-running":
            step.long_running = True
        if mark and mark[0] == "expect-exit":
            code = re.match(r"\d+", mark[1])
            if code:
                step.expect_exit = int(code.group())
        kept.append(step)
    for i, step in enumerate(kept, 1):
        step.index = i
    plan.steps = kept
    return plan


def program_of(command: str) -> str:
    """What a command runs, e.g. `python -m tool_x` or `python main.py`, ignoring its arguments."""
    try:
        tokens = shlex.split(command.replace("\\\n", " "))
    except ValueError:
        tokens = command.split()
    tokens = [t for t in tokens if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", t)]
    if not tokens:
        return ""
    if tokens[0] in ("python", "python3", "py") and len(tokens) > 1:
        if tokens[1] == "-m" and len(tokens) > 2:
            return " ".join(tokens[:3])
        return " ".join(tokens[:2])
    return tokens[0]


def documented_output(readme_text: str, line: Optional[int]) -> Optional[str]:
    """What the README shows the command on `line` printing, if it shows anything.

    Either the rest of a console transcript (`$ cmd` followed by its output) or an output-only
    block that comes right after the command's block.
    """
    if not line:
        return None
    blocks = parse_code_blocks(readme_text)
    for i, b in enumerate(blocks):
        numbers = [ln for ln, _ in b["lines"]]
        if line not in numbers:
            continue
        raw = dict(b["lines"])[line]
        if raw.strip().startswith("$"):
            out = []
            for ln, text in b["lines"]:
                if ln <= line:
                    continue
                if text.strip().startswith("$ "):
                    break
                out.append(text)
            if "\n".join(out).strip():
                return "\n".join(out).strip("\n")
        if i + 1 < len(blocks):
            nxt = blocks[i + 1]
            if nxt["start"] - b["end"] <= 8 and nxt["code"].strip() and not _block_commands(nxt):
                return nxt["code"].strip("\n")
        return None
    return None


def locate_line(readme_text: str, command: str) -> Optional[int]:
    """1-based README line where a command (its first line) is written."""
    if not command.strip():
        return None
    first = command.strip().splitlines()[0].strip()
    lines = readme_text.splitlines()
    for idx, line in enumerate(lines, 1):
        s = line.strip()
        m = PROMPT_RE.match(s)
        if m and s.startswith(("$", "(")):
            s = m.group(1).strip()
        if strip_comment(s) == first or s == first:
            return idx
    for idx, line in enumerate(lines, 1):
        if first in line:
            return idx
    return None


def extract_plan(project_dir: Path) -> Plan:
    """Rule based plan: the commands a Linux newcomer would type, in README order."""
    readme = find_readme(project_dir)
    if readme is None:
        return Plan(steps=[], notes=["No README found in the project folder."])
    text = read_text(readme) or ""
    rel = readme.relative_to(project_dir).as_posix()
    plan = Plan(steps=[], readme_path=rel, engine="rules")
    if readme.suffix.lower() not in (".md", ".markdown", ""):
        plan.notes.append(f"{rel} is not Markdown, only fenced code blocks are understood.")

    blocks = parse_code_blocks(text)
    prereq_prose = _prereq_prose(text)
    clone_dirs: set[str] = set()
    created: set[str] = set()
    seen: dict[str, int] = {}
    installed_tools: set[str] = set()
    last_was_clone = False
    steps: list[Step] = []

    def add_step(command: str, line: Optional[int], section: str, provided: bool = False) -> None:
        word = command_word(command)
        steps.append(Step(
            index=len(steps) + 1,
            command=command,
            kind="prerequisite" if provided else _kind(command, word, section),
            section=section,
            line=line,
            long_running=_long_running(command, project_dir),
            provided_by_firstrun=provided,
            purpose="documented prerequisite installed by FirstRun" if provided else "",
        ))

    for block in blocks:
        for item in _block_commands(block):
            command, line, section = item["command"], item["line"], block["section"]
            word = command_word(command)
            if item["os"] == "windows" or WINDOWS_RE.search(command):
                plan.skipped.append(Skipped(command, "windows-only (FirstRun runs Linux)", line))
                continue
            if item["os"] == "macos" or word == "brew":
                plan.skipped.append(Skipped(command, "macOS-only (FirstRun runs Linux)", line))
                continue
            if re.match(r"^git\s+clone\b", command):
                args = [a for a in command.split()[2:] if not a.startswith("-")]
                if len(args) >= 2:
                    clone_dirs.add(args[1])
                elif args:
                    clone_dirs.add(re.sub(r"\.git$", "", args[0].rstrip("/").split("/")[-1]))
                plan.skipped.append(Skipped(command, "git clone (project is already checked out)", line))
                last_was_clone = True
                continue
            cd = _cd_target(command)
            if cd:
                target, rest = cd
                reason = _skip_cd(target, project_dir, clone_dirs, created)
                if reason is None and last_was_clone and not (project_dir / target).is_dir():
                    reason = "cd into the cloned repo (project is already the working directory)"
                if reason:
                    plan.skipped.append(Skipped(f"cd {target}", reason, line))
                    last_was_clone = False
                    if not rest:
                        continue
                    command, word = rest, command_word(rest)
            last_was_clone = False
            if word != "cd" and command in seen:
                plan.skipped.append(Skipped(command, f"duplicate of step {seen[command]}", line))
                continue
            for m in re.finditer(r"\bmkdir\s+(?:-p\s+)?(\S+)|\b(?:-m\s+venv|virtualenv|uv\s+venv)\s+(\S+)", command):
                created.add((m.group(1) or m.group(2)).strip("\"'").split("/")[0])
            if word in PACKAGE_MANAGERS and word not in installed_tools:
                if re.search(rf"\b{re.escape(word)}\b", prereq_prose, re.I):
                    add_step(PACKAGE_MANAGERS[word], None, "Prerequisites", provided=True)
                installed_tools.add(word)
            m = re.search(r"\bpip3?\s+install\s+(.*)", command)
            if m:
                installed_tools.update(t for t in PACKAGE_MANAGERS if re.search(rf"\b{t}\b", m.group(1)))
            add_step(command, line, section)
            seen[command] = steps[-1].index

    plan.steps = steps
    apply_directives(plan, text)
    plan.required_env = _secret_envs(project_dir, text)
    plan.expected_output = _expected_output(blocks)
    for s in steps:
        m = re.match(r"^export\s+([A-Za-z_][A-Za-z0-9_]*)=(.*)$", s.command)
        if m and PLACEHOLDER_RE.search(m.group(2)):
            plan.notes.append(
                f"Step {s.index} sets {m.group(1)} to a placeholder; supply the real value with --env-file."
            )
    if not steps:
        plan.notes.append(f"No runnable shell commands found in {rel}.")
    return plan
