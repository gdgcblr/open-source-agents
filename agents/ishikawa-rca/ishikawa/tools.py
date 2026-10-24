"""Evidence tools the investigators call.

Every tool reads the active incident from session state (`incident_id`), so one
agent graph can investigate any incident. Data comes from `fixtures/<id>.json`.
If `repo_path` is set in state, the deploy and diff tools read the real git
history of that repository instead (read-only `git log` / `git show`).
"""

from __future__ import annotations

import json
import re
import subprocess
from functools import lru_cache
from pathlib import Path

from google.adk.tools import ToolContext

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"
_SHA_RE = re.compile(r"^[0-9a-zA-Z][0-9a-zA-Z_-]{3,39}$")


def list_incidents() -> list[dict]:
    """Return id and title of every recorded incident fixture."""
    out = []
    for path in sorted(FIXTURES_DIR.glob("*.json")):
        data = json.loads(path.read_text())
        out.append({"id": data["id"], "title": data["title"], "service": data["alert"]["service"]})
    return out


@lru_cache(maxsize=16)
def load_incident(incident_id: str) -> dict:
    path = FIXTURES_DIR / f"{incident_id}.json"
    if not re.fullmatch(r"[a-z0-9-]+", incident_id) or not path.exists():
        raise ValueError(f"Unknown incident '{incident_id}'. Known: {[i['id'] for i in list_incidents()]}")
    return json.loads(path.read_text())


def _incident(tool_context: ToolContext) -> dict:
    return load_incident(tool_context.state.get("incident_id", "checkout-latency"))


def _git(repo: str, *args: str) -> str:
    """Run a read-only git command; errors come back as text so one bad sha can't abort the run."""
    try:
        return subprocess.run(
            ["git", "-C", repo, *args], capture_output=True, text=True, timeout=20, check=True
        ).stdout
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        return f"git error: {getattr(e, 'stderr', '') or e}"


# --- tools exposed to agents -------------------------------------------------


def get_alert(tool_context: ToolContext) -> dict:
    """Get the alert that triggered this investigation: service, policy, observed values, fire time."""
    return _incident(tool_context)["alert"]


def list_recent_deploys(tool_context: ToolContext) -> list[dict]:
    """List recent deploys/commits (newest first) with sha, author, time, revision and changed files."""
    repo = tool_context.state.get("repo_path")
    if repo:
        raw = _git(repo, "log", "-n", "15", "--date=iso-strict", "--name-only",
                   "--pretty=format:%x1e%h%x1f%an%x1f%ad%x1f%s")
        if raw.startswith("git error"):
            return [{"error": raw}]
        deploys = []
        for block in raw.split("\x1e")[1:]:
            head, *files = block.strip("\n").splitlines()
            sha, author, date, msg = head.split("\x1f", 3)
            deploys.append({"sha": sha, "author": author, "deployed_at": date,
                            "message": msg, "files": [f for f in files if f]})
        return deploys
    return _incident(tool_context)["deploys"]


def get_commit_diff(sha: str, tool_context: ToolContext) -> str:
    """Get the unified diff for one commit/deploy sha from list_recent_deploys."""
    if not _SHA_RE.match(sha):
        return "invalid sha"
    repo = tool_context.state.get("repo_path")
    if repo:
        return _git(repo, "show", "--stat", "--patch", "--no-color", "--end-of-options", sha)[:12000]
    return _incident(tool_context)["diffs"].get(sha, f"no diff recorded for {sha}")


def search_logs(query: str, tool_context: ToolContext, severity: str = "") -> list[dict]:
    """Search service logs. `query` is a case-insensitive substring ('' returns all);
    optional `severity` filters by DEBUG/INFO/WARNING/ERROR."""
    q, sev = query.lower(), severity.upper()
    return [
        line for line in _incident(tool_context)["logs"]
        if q in line["message"].lower() and (not sev or line["severity"] == sev)
    ]


def get_metrics(tool_context: ToolContext) -> dict:
    """Get infrastructure/service metrics with before/after values and when each changed."""
    return _incident(tool_context)["metrics"]


def get_config_changes(tool_context: ToolContext) -> list[dict]:
    """Get environment-variable / runtime config changes per Cloud Run revision."""
    return _incident(tool_context)["config_revisions"]


def get_dependency_changes(tool_context: ToolContext) -> dict:
    """Get package/lockfile version changes in the recent window."""
    return _incident(tool_context)["dependencies"]


def get_traffic(tool_context: ToolContext) -> dict:
    """Get request volume before/after, traffic notes, and top endpoints."""
    return _incident(tool_context)["traffic"]


def get_database_stats(tool_context: ToolContext) -> dict:
    """Get database CPU, connections, top queries and schema migrations."""
    return _incident(tool_context)["database"]


ALL_TOOLS = [
    get_alert, list_recent_deploys, get_commit_diff, search_logs, get_metrics,
    get_config_changes, get_dependency_changes, get_traffic, get_database_stats,
]
