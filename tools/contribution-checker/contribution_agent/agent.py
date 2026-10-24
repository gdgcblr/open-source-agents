import os
from dataclasses import asdict
from pathlib import Path
from google.adk.agents import Agent
from checker.rules import run_all

def run_checks(project_path: str) -> dict:
    """Run all contribution checks on a project folder and return the results."""
    p = Path(project_path).resolve()
    if not p.is_dir():
        return {"error": f"{project_path} is not a directory"}
    return {"results": [asdict(r) for r in run_all(p)]}

root_agent = Agent(
    name="contribution_checker",
    model=os.getenv("MODEL_NAME", "gemini-3.8-flash"),
    description="Checks a contribution folder against the repo's rules.",
    instruction=(
        "You help contributors prepare pull requests. When given a project path, "
        "call run_checks. Then summarize which checks passed, and for each failure "
        "explain the problem and give one concrete fix. Use only the tool results; "
        "do not invent rules."
    ),
    tools=[run_checks],
)