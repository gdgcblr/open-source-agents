"""Deny-by-default policy: which tools (and which `exec` commands) may receive which secrets.

Keys are ADK tool names, or `exec:<command>` for `d3v-keyguard exec` (command = program
name without directory or extension, lower-case, e.g. `exec:gh`, `exec:npm`; or a full
program path). `exec` is unrestricted unless the policy contains at least one `exec:` key;
then it is deny-by-default.

Tool names are matched by name only: every tool with that name, in any agent, sub-agent
or toolset (including MCP toolsets), is treated as the same tool.
"""

from __future__ import annotations

import fnmatch
import json
import os
from pathlib import Path


class Policy:
    def __init__(self, rules: dict[str, list[str]] | None = None):
        self.rules = {tool: list(patterns) for tool, patterns in (rules or {}).items()}

    def allows(self, tool_name: str, secret_name: str) -> bool:
        return any(fnmatch.fnmatchcase(secret_name, p) for p in self.rules.get(tool_name, []))

    @property
    def restricts_exec(self) -> bool:
        return any(k.startswith("exec:") for k in self.rules)

    def allows_exec(self, command: str, secret_name: str, *, from_path: bool = True) -> bool:
        """`command` is the resolved program path. A bare-name rule (`exec:gh`) only covers
        programs found through PATH; a program given as an explicit path (e.g. `.\\gh.cmd`)
        needs a rule keyed by its full path (`exec:C:\\tools\\gh.cmd`)."""
        if not self.restricts_exec:
            return True
        full = os.path.normcase(os.path.abspath(command))
        for key in self.rules:
            path = key[5:] if key.startswith("exec:") else ""
            if os.path.isabs(path) and os.path.normcase(os.path.abspath(path)) == full:
                if self.allows(key, secret_name):
                    return True
        return from_path and self.allows("exec:" + Path(command).stem.lower(), secret_name)

    @classmethod
    def from_file(cls, path: str | os.PathLike) -> "Policy":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not all(
            isinstance(v, list) and all(isinstance(p, str) for p in v) for v in data.values()
        ):
            raise ValueError("policy file must map tool names to lists of glob patterns")
        return cls(data)

    @classmethod
    def from_env(cls) -> "Policy":
        path = os.environ.get("KEYGUARD_POLICY_FILE")
        return cls.from_file(path) if path else cls()
