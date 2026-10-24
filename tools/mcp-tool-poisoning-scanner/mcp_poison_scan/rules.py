"""Heuristic rules that flag poisoned MCP tool definitions."""

import base64
import binascii
import re
from dataclasses import asdict, dataclass

from .unicode_checks import decode_tag_chars, find_invisible

SEVERITIES = ("low", "medium", "high")

INJECTION_PATTERNS = [
    (r"ignore\s+(all\s+|any\s+)?(previous|prior|above|earlier)\s+(instructions|prompts|rules)", "asks the model to ignore previous instructions"),
    (r"(do\s+not|don'?t|never)\s+(tell|mention|inform|notify|reveal|show)\b[^.\n]{0,40}\buser", "asks the model to hide actions from the user"),
    (r"<\s*/?\s*(important|system|instructions?|secret|hidden)\s*>", "contains a fake instruction tag"),
    (r"before\s+(using|calling|invoking)\s+(this|the|any)\s+tool", "gives pre-conditions the model must perform first"),
    (r"you\s+(must|have\s+to|need\s+to)\s+(first\s+)?(read|call|run|execute|send|include|pass|fetch)", "orders the model to take an action"),
    (r"(otherwise|or\s+else)\s+the\s+tool\s+will\s+(not\s+work|fail|crash)", "uses a coercive threat to force compliance"),
    (r"\b(you\s+are\s+now|act\s+as|new\s+instructions|system\s+prompt\s*:)", "attempts a role or instruction override"),
    (r"\b(always|must)\s+(call|use|invoke|run|execute)\s+this\s+tool\b", "forces the model to always call this tool"),
    (r"\b(after|before|following)\s+(any|every|each|all)\s+(other\s+)?(actions?|tools?|tool\s+calls?|calls?|requests?|responses?)\b"
     r"|\bevery\s+time\s+(a|any|another)\s+(other\s+)?tool\s+is\s+(used|called|invoked|run)\b",
     "hooks into every other tool call"),
]

SENSITIVE_PATTERNS = [
    r"~?/?\.ssh\b", r"\bid_(rsa|ed25519|ecdsa|dsa)\b", r"(^|[\s/`'\"])\.env\b",
    r"\.aws/credentials", r"\.netrc\b", r"\.git-credentials", r"\.kube/config",
    r"\bmcp\.json\b", r"claude_desktop_config\.json", r"/etc/(passwd|shadow)",
    r"cookies\.sqlite|Login Data|\bKeychain\b", r"\b(api[_\s-]?keys?|private[_\s-]?keys?|access[_\s-]?tokens?)\b",
]

EXFIL_PARAM_NAMES = {
    "sidenote", "side_note", "note", "notes", "context", "extra", "metadata", "debug",
    "conversation", "conversation_history", "history", "chat_history", "system_prompt",
    "instructions", "feedback", "summary",
}
# Data from the model's own context that a tool should never need.
EXFIL_DESC_PATTERN = re.compile(
    r"(conversation|chat)\s+history|previous\s+(messages|turns)|system\s+prompt"
    r"|full\s+(context|conversation|transcript)|everything\s+the\s+user\s+(said|typed)"
    # Capturing what *other* tools received or returned.
    r"|\b(arguments|args|inputs|parameters|results?|outputs?|responses?)\s+(passed\s+to|sent\s+to|returned\s+by|"
    r"received\s+from|from)\s+(the|an?|another|other|any|each|every)\s+(\w+\s+)?tools?\b"
    r"|\b(data|information|details)\s+(\w+\s+)?(from|in|during)\s+the\s+(interaction|conversation|session|chat)\b",
    re.I,
)

SHADOW_PATTERN = r"(when|whenever|if|before|after)\b[^.\n]{0,60}\b{name}\b[^.\n]{0,80}\b(instead|always|also|change|redirect|replace|bcc|cc|override|must)\b"

GENERIC_TOOL_REF = r"(?P<other>[A-Za-z_][\w.-]*)\s+tool"
NOT_TOOL_NAMES = {"this", "the", "a", "an", "any", "that", "other", "each", "every", "same"}

ENCODED_PATTERNS = [
    (re.compile(r"[A-Za-z0-9+/]{40,}={0,2}"), "base64"),
    (re.compile(r"\b(?:[0-9a-fA-F]{2}){24,}\b"), "hex"),
]
URL_PATTERN = re.compile(r"(https?|ftp|file|data):[^\s'\"`)>]*", re.I)


@dataclass
class Finding:
    rule_id: str
    severity: str
    tool: str
    path: str
    message: str
    evidence: str = ""
    server: str = ""

    def to_dict(self):
        return asdict(self)


def _snippet(text, start, end, width=40):
    left = max(0, start - width)
    right = min(len(text), end + width)
    snippet = text[left:right].replace("\n", " ")
    return ("…" if left else "") + snippet + ("…" if right < len(text) else "")


def iter_strings(value, path=""):
    """Yield (path, string) for every string in a JSON value, including dict keys."""
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for key, item in value.items():
            child = f"{path}.{key}" if path else str(key)
            if isinstance(key, str) and find_invisible(key):
                yield child + "<key>", key
            yield from iter_strings(item, child)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from iter_strings(item, f"{path}[{index}]")


def _check_hidden_unicode(tool_name, path, text):
    hidden = find_invisible(text)
    if not hidden:
        return []
    kinds = sorted({kind for _, _, kind in hidden})
    decoded = decode_tag_chars(text)
    evidence = f"hidden message: {decoded!r}" if decoded else ", ".join(cp for _, cp, _ in hidden[:10])
    return [Finding("HIDDEN_UNICODE", "high", tool_name, path,
                    f"{len(hidden)} invisible character(s) ({', '.join(kinds)})", evidence)]


def _check_patterns(tool_name, path, text):
    findings = []
    # Strip invisible chars so they can't be used to split keywords.
    visible = "".join(c for c in text if not find_invisible(c))
    smuggled = decode_tag_chars(text)
    for candidate in filter(None, (visible, smuggled)):
        for pattern, reason in INJECTION_PATTERNS:
            match = re.search(pattern, candidate, re.I)
            if match:
                findings.append(Finding("INSTRUCTION_INJECTION", "high", tool_name, path, reason,
                                        _snippet(candidate, match.start(), match.end())))
        for pattern in SENSITIVE_PATTERNS:
            match = re.search(pattern, candidate, re.I)
            if match:
                findings.append(Finding("SENSITIVE_RESOURCE", "high", tool_name, path,
                                        f"references sensitive resource {match.group(0).strip()!r}",
                                        _snippet(candidate, match.start(), match.end())))
        findings += _check_encoded(tool_name, path, candidate)
    return findings


def _decode_printable(blob, label):
    try:
        raw = bytes.fromhex(blob) if label == "hex" else base64.b64decode(blob + "=" * (-len(blob) % 4))
        text = raw.decode("utf-8")
    except (binascii.Error, ValueError):
        return None
    return text if text.isprintable() else None


def _check_encoded(tool_name, path, text):
    # URLs and data URIs legitimately contain long base64-looking runs.
    stripped = URL_PATTERN.sub(" ", text)
    for pattern, label in ENCODED_PATTERNS:
        for match in pattern.finditer(stripped):
            blob = match.group(0)
            decoded = _decode_printable(blob.rstrip("="), label)
            if label == "base64" and decoded is None and "/" in blob:
                continue  # most likely a file path, not a payload
            evidence = f"decodes to: {decoded!r}" if decoded else _snippet(stripped, match.start(), match.end(), 10)
            return [Finding("ENCODED_PAYLOAD", "medium", tool_name, path,
                            f"contains a long {label} blob that may hide instructions", evidence)]
    return []


def _check_exfil_params(tool_name, tool):
    findings = []
    properties = (tool.get("inputSchema") or {}).get("properties") or {}
    for param, schema in properties.items():
        description = (schema or {}).get("description", "") if isinstance(schema, dict) else ""
        name_suspicious = param.lower() in EXFIL_PARAM_NAMES
        desc_match = EXFIL_DESC_PATTERN.search(description)
        if desc_match or (name_suspicious and re.search(rf"\b{re.escape(param)}\b", tool.get("description", ""), re.I)):
            reason = f"parameter {param!r} asks for data unrelated to the tool" if desc_match else \
                f"tool description instructs the model to fill parameter {param!r}"
            findings.append(Finding("EXFIL_PARAMETER", "medium", tool_name,
                                    f"inputSchema.properties.{param}", reason, description[:120]))
    return findings


def _check_shadowing(tool_name, tool, other_names):
    findings = []
    description = tool.get("description", "") or ""
    text = description + " " + decode_tag_chars(description)
    for other in other_names:
        if other == tool_name:
            continue
        match = re.search(SHADOW_PATTERN.replace("{name}", re.escape(other)), text, re.I)
        if match:
            findings.append(Finding("TOOL_SHADOWING", "high", tool_name, "description",
                                    f"tries to change how the {other!r} tool behaves",
                                    _snippet(text, match.start(), match.end())))
    if not findings:
        # The target tool may live on a server we did not scan, so match "the <x> tool" too.
        for match in re.finditer(SHADOW_PATTERN.replace("{name}", GENERIC_TOOL_REF), text, re.I):
            other = match.group("other")
            if other.lower() not in NOT_TOOL_NAMES and other != tool_name:
                findings.append(Finding("TOOL_SHADOWING", "medium", tool_name, "description",
                                        f"tries to change how another tool ({other!r}) behaves",
                                        _snippet(text, match.start(), match.end())))
                break
    return findings


def scan_tools(tools, server="", max_description=1000, known_tool_names=None):
    """Scan one server's tool list. known_tool_names adds names from other servers for shadowing checks."""
    names = {t.get("name", "") for t in tools if isinstance(t, dict)}
    other_names = names | set(known_tool_names or ())
    findings = []
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        tool_name = str(tool.get("name", "<unnamed>"))
        for path, text in iter_strings(tool):
            findings += _check_hidden_unicode(tool_name, path, text)
            findings += _check_patterns(tool_name, path, text)
        findings += _check_exfil_params(tool_name, tool)
        findings += _check_shadowing(tool_name, tool, other_names)
        description = tool.get("description") or ""
        if len(description) > max_description:
            findings.append(Finding("OVERLONG_DESCRIPTION", "low", tool_name, "description",
                                    f"description is {len(description)} characters (limit {max_description})"))
    for finding in findings:
        finding.server = server
    return _dedupe(findings)


def scan_servers(servers, max_description=1000):
    """Scan {server_name: tools}, including cross-server shadowing and duplicate names."""
    all_names = {}
    for server, tools in servers.items():
        for tool in tools:
            if isinstance(tool, dict) and tool.get("name"):
                all_names.setdefault(tool["name"], []).append(server)
    findings = []
    for server, tools in servers.items():
        findings += scan_tools(tools, server, max_description, known_tool_names=all_names)
    for name, owners in all_names.items():
        if len(owners) > 1:
            findings.append(Finding("TOOL_SHADOWING", "medium", name, "name",
                                    f"tool name is defined by several servers: {', '.join(owners)}",
                                    server=owners[-1]))
    return findings


def _dedupe(findings):
    seen = set()
    unique = []
    for f in findings:
        key = (f.rule_id, f.server, f.tool, f.path, f.message)
        if key not in seen:
            seen.add(key)
            unique.append(f)
    return unique
