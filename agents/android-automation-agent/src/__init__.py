"""Android automation agent package (Google ADK).

ADK discovers ``root_agent`` through ``agent.py``; importing it here follows the
standard ADK project layout. The import is skipped only when ``google-adk``
itself is not installed, so the tool adapter and its tests stay importable.
"""

try:
    from . import agent  # noqa: F401  (exposes root_agent to ADK)
except ModuleNotFoundError as exc:  # pragma: no cover - depends on environment
    if (exc.name or "").split(".")[0] != "google":
        raise
