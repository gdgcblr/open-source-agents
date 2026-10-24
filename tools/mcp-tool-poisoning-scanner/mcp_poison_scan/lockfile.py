"""Pin tool definitions by hash to detect silent changes ("rug-pulls")."""

import hashlib
import json

from .rules import Finding

LOCK_VERSION = 1


def tool_hash(tool):
    canonical = json.dumps(tool, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_lock(servers):
    return {
        "version": LOCK_VERSION,
        "servers": {
            server: {tool["name"]: tool_hash(tool) for tool in tools if isinstance(tool, dict) and "name" in tool}
            for server, tools in servers.items()
        },
    }


def diff_lock(lock, servers):
    """Compare current tools against a lock. Servers not in the lock are skipped."""
    findings = []
    pinned_servers = lock.get("servers", {})
    for server, tools in servers.items():
        if server not in pinned_servers:
            continue
        pinned = pinned_servers[server]
        current = {t["name"]: tool_hash(t) for t in tools if isinstance(t, dict) and "name" in t}
        for name, digest in current.items():
            if name not in pinned:
                findings.append(Finding("RUG_PULL", "medium", name, "", "tool was added since it was pinned",
                                        digest, server))
            elif pinned[name] != digest:
                findings.append(Finding("RUG_PULL", "high", name, "",
                                        "tool definition changed since it was pinned",
                                        f"{pinned[name]} -> {digest}", server))
        for name in pinned.keys() - current.keys():
            findings.append(Finding("RUG_PULL", "low", name, "", "tool was removed since it was pinned",
                                    pinned[name], server))
    return findings
