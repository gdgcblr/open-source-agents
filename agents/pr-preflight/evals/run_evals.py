"""Run PR Preflight on each eval fixture and score it against expected.json.

Usage:
  python evals/run_evals.py                       # all fixtures (full pipeline)
  python evals/run_evals.py --only leaked_key     # one fixture
  python evals/run_evals.py --only leaked_key --checks-only   # no LLM
"""
import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(ROOT))

from checks import print_results, run_checks  # noqa: E402

# Intentionally fake key for eval fixture
FAKE_KEY = "AIza" + "FAKE" * 8 + "FAK"
PLACEHOLDER = "__FAKE_KEY_PLACEHOLDER__"


def materialize_fixture(name: str) -> Path:
    """Copy a fixture to a temp dir, injecting the fake key where needed."""
    dest = Path(tempfile.mkdtemp(prefix="preflight_fixture_")) / name
    shutil.copytree(FIXTURES / name, dest, ignore=shutil.ignore_patterns("expected.json"))
    for f in dest.rglob("*.py"):
        text = f.read_text(encoding="utf-8")
        if PLACEHOLDER in text:
            f.write_text(text.replace(PLACEHOLDER, FAKE_KEY), encoding="utf-8")
    return dest


def remove_fixture(path: Path) -> None:
    shutil.rmtree(path.parent, ignore_errors=True)


def load_expected(name: str) -> dict:
    exp = json.loads((FIXTURES / name / "expected.json").read_text(encoding="utf-8"))
    exp["must_not_contain"] = [FAKE_KEY if s == "$FAKE_KEY" else s
                               for s in exp.get("must_not_contain", [])]
    return exp


def checks_only(name: str) -> None:
    path = materialize_fixture(name)
    try:
        results = run_checks(str(path))
        print(f"== {name} ==")
        print_results(results)
        output = json.dumps(results)
        leaked = [s for s in load_expected(name)["must_not_contain"] if s in output]
        print("secret leak in output!" if leaked else "no secret leaked in output")
    finally:
        remove_fixture(path)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="run a single fixture by folder name")
    ap.add_argument("--checks-only", action="store_true", help="skip sandbox + LLM")
    args = ap.parse_args()
    names = [args.only] if args.only else sorted(p.name for p in FIXTURES.iterdir() if p.is_dir())
    for name in names:
        if args.checks_only:
            checks_only(name)
        else:
            sys.exit("Full eval loop arrives in Phase 5; use --checks-only for now.")


if __name__ == "__main__":
    main()
