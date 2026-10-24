"""Before/after demo (offline, no key): review a weak README, apply the fixes the report asks
for, review again.

Run from the project folder:   python evals/demo_before_after.py
The fixes are applied by this script (the reviewer never edits files); it adds the dependency
manifest, .env.example and the missing README sections the first report lists.
"""

import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
sys.path[:0] = [str(HERE), str(PROJECT)]
os.environ["PR_SCOPE"] = "off"  # the git scope check depends on repo state
os.chdir(PROJECT)

from cases import SAMPLES  # noqa: E402
from review_core.analysis.checks import run_deterministic_checks  # noqa: E402
from review_core.analysis.scoring import build_report  # noqa: E402

DEMO = HERE / ".generated" / "demo" / "note-summarizer"

MISSING_SECTIONS = """
## Prerequisites
- Python 3.11 or newer
- An API key for the summarizer service

## Installation & Setup
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## Configuration & Environment Variables
| Variable | Required | Description |
| :--- | :--- | :--- |
| `SUMMARY_API_KEY` | Yes | Key for the summarizer service |

## How to Run
```bash
python main.py notes.txt
```
"""


def review():
    return build_report(run_deterministic_checks(DEMO.relative_to(PROJECT).as_posix())["checks"])


def show(title, report):
    print(f"\n{title}: score {report.overall_score}, verdict {report.verdict}")
    print("  criteria:", report.criterion_scores.model_dump(exclude_none=True))
    for failure in report.failures:
        print(f"  FAIL {failure.id}: {failure.reason}")


def apply_fixes():
    (DEMO / "requirements.txt").write_text("requests==2.32.3\n")
    (DEMO / ".env.example").write_text("SUMMARY_API_KEY=your_api_key_here\n")
    readme = DEMO / "README.md"
    readme.write_text(readme.read_text().rstrip("\n") + "\n" + MISSING_SECTIONS)


def main():
    if DEMO.parent.exists():
        shutil.rmtree(DEMO.parent)
    shutil.copytree(SAMPLES / "missing-install-agent", DEMO)
    show("BEFORE", review())
    apply_fixes()
    show("AFTER", review())


if __name__ == "__main__":
    main()
