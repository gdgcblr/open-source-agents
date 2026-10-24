"""Per-criterion tools for the review team.

Each tool runs only its own criterion's deterministic checks, saves them in session
state (the finalizer scores from there), and returns them with that criterion's score.
"""

from google.adk.tools.tool_context import ToolContext

from .analysis.checks import run_deterministic_checks
from .analysis.scoring import score_checks


def _review(criterion: str, path: str, tool_context: ToolContext) -> dict:
    result = run_deterministic_checks(path, [criterion])
    if "error" in result:
        tool_context.state["review_error"] = result["error"]  # shown by the finalizer
        return result
    tool_context.state[f"checks_{criterion}"] = result["checks"]
    tool_context.state["review_project"] = result["project"]
    _, scores = score_checks(result["checks"])
    return {"criterion": criterion, "score": scores.get(criterion), "checks": result["checks"]}


def review_reproducibility(path: str, tool_context: ToolContext) -> dict:
    """Run the reproducibility checks (manifest, .env.example, pinned deps, Python version, run command).

    Args:
        path: Folder name or path of the project to review.
    """
    return _review("reproducibility", path, tool_context)


def review_documentation(path: str, tool_context: ToolContext) -> dict:
    """Run the documentation checks (sections, placeholders, thin sections, commands, links).

    Args:
        path: Folder name or path of the project to review.
    """
    return _review("documentation", path, tool_context)


def review_security(path: str, tool_context: ToolContext) -> dict:
    """Run the security checks (secrets, .gitignore coverage, risky code).

    Args:
        path: Folder name or path of the project to review.
    """
    return _review("security", path, tool_context)


def review_scope(path: str, tool_context: ToolContext) -> dict:
    """Run the scope checks (folder name, PR scope).

    Args:
        path: Folder name or path of the project to review.
    """
    return _review("scope", path, tool_context)
