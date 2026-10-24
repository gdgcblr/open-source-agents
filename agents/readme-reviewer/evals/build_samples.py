"""Build the eval sample projects and the ADK eval set.

Run from the project folder:   python evals/build_samples.py

Writes evals/.generated/ (git-ignored; holds the fake-key sample) and
evals/readme_reviewer.evalset.json. Each case asks the agent to review one sample; the expected
final response is the deterministic report, which is computed from code and so is repeatable.
"""

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
sys.path[:0] = [str(HERE), str(PROJECT)]
os.environ["PR_SCOPE"] = "off"  # the git scope check depends on repo state, so evals skip it
os.chdir(PROJECT)

from google.adk.evaluation.eval_case import EvalCase, Invocation  # noqa: E402
from google.adk.evaluation.eval_set import EvalSet  # noqa: E402
from google.genai import types  # noqa: E402

from cases import CASES, build_samples  # noqa: E402
from review_core.analysis.checks import run_deterministic_checks  # noqa: E402
from review_core.analysis.scoring import build_report  # noqa: E402

GENERATED = HERE / ".generated"
EVALSET = HERE / "readme_reviewer.evalset.json"


def content(role: str, text: str) -> types.Content:
    return types.Content(role=role, parts=[types.Part(text=text)])


def main() -> None:
    build_samples(GENERATED)
    eval_cases = []
    for case in CASES:
        folder = (GENERATED / case["folder"]).relative_to(PROJECT).as_posix()
        report = build_report(run_deterministic_checks(folder)["checks"])
        invocation = Invocation(
            invocation_id=f"{case['id']}-1",
            user_content=content("user", f"Review {folder}"),
            final_response=content("model", report.model_dump_json(indent=2)),
        )
        eval_cases.append(EvalCase(eval_id=case["id"], conversation=[invocation]))
    eval_set = EvalSet(
        eval_set_id="readme_reviewer",
        name="README reviewer samples",
        description="Five sample projects: excellent, missing install steps, leaked key, wrong folder name, minimal.",
        eval_cases=eval_cases,
    )
    EVALSET.write_text(eval_set.model_dump_json(indent=2, exclude_none=True) + "\n")
    print(f"Wrote {len(eval_cases)} cases to {EVALSET.relative_to(PROJECT)} and samples to {GENERATED.relative_to(PROJECT)}/")


if __name__ == "__main__":
    main()
