# Verification — git-commit-assistant

All commands run on Windows (PowerShell), Python 3.12.10, from the workspace
root `c:\Users\A555902\Downloads\open-source-agents`. No API key set; no network.

## 1. Mock run prints a sensible Conventional Commits message

Command:
```
python agents\git-commit-assistant\main.py --diff-file agents\git-commit-assistant\tests\fixtures\add_module.diff
```
Output (exit 0, auto-selected mock because no OPENAI_API_KEY):
```
feat(commit_assistant): add greet module

- add commit_assistant/greet.py (+6/-0)
```

Additional real runs:
```
python agents\git-commit-assistant\main.py --diff-file ...\docs_only.diff --provider mock
-> docs(README): update README.md documentation
   (blank line)
   - update README.md (+2/-0)      [exit 0]

python agents\git-commit-assistant\main.py --diff-file ...\fix_bug.diff --provider mock
-> fix(src): update handler.py
   (blank line)
   - update src/bugfix/handler.py (+3/-1)   [exit 0]
```

The blank line between header and body was confirmed present via a raw-byte
check: `feat(commit_assistant): add greet module<NL><NL>- add ... (+6/-0)<NL>`.

## 2. Test suite — all pass, no network, no real git

First installed the dev dependency:
```
python -m pip install pytest==8.3.3
```
Command:
```
python -m pytest agents\git-commit-assistant\tests -q
```
Output:
```
.......................................
..
41 passed in 0.11s
```

## 3. Error paths

- No API key required for any of the above to pass (confirmed: auto -> mock).
- Missing diff file:
  ```
  python agents\git-commit-assistant\main.py --diff-file nope.diff --provider mock
  -> error: Diff file not found: nope.diff        [exit 2]
  ```
- Empty diff -> friendly "No staged changes found." message with exit 1
  (covered by test_cli.test_cli_empty_diff_file).

## 4. Cleanup

Removed all `__pycache__/` and `.pytest_cache/` artifacts from the project
folder after the run. No `.venv` or `.env` was created inside the project
folder. No secrets committed.
