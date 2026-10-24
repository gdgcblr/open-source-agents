#!/usr/bin/env bash
# Runs the real agent end to end on the sample projects with `adk eval`.
# Needs: pip install -r requirements-eval.txt, and a model key in .env (the team makes several
# model calls per case, so use NVIDIA or a billed Gemini key rather than the free tier).
set -euo pipefail
cd "$(dirname "$0")/.."
python evals/build_samples.py
# PYTHONPATH: adk eval does not add this folder to sys.path, and the team imports readme_reviewer.
PYTHONPATH=. PR_SCOPE=off adk eval readme_reviewer_team evals/readme_reviewer.evalset.json \
  --config_file_path evals/test_config.json --print_detailed_results
