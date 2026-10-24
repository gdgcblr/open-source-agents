# Example review: getredash/redash#7882

A real, unedited run of PR Slop Detector against a public pull request.

| | |
| :--- | :--- |
| **PR** | [getredash/redash#7882](https://github.com/getredash/redash/pull/7882): "Stop sending alert emails to disabled users" |
| **Reviewed on** | 2026-10-24 |
| **Model** | `gemma4:e2b-it-qat` via local Ollama (default backend) |
| **Machine** | Apple M2, 8 GB RAM, macOS |
| **Run time** | 4.0 min (LLM review); the heuristics pass is instant |
| **Result** | 🟢 Looks good, 16/100 |

Nothing was posted to the PR. This was a read-only, local review.

## Command used

Run from `tools/pr-slop-detector/` with the virtual environment active. The review was done in two steps: first fetch the PR from GitHub and save it (heuristics only), then run the full local Gemma review on the saved copy:

```bash
# 1. Fetch the PR read-only, run heuristics, and save the PR data for re-runs
GITHUB_TOKEN=$(gh auth token) python -m slop_detector \
  "https://github.com/getredash/redash/pull/7882" --no-llm --save-json redash_7882.json

# 2. Full review (heuristics + local Gemma 4 agent) on the saved PR
python -m slop_detector --from-json redash_7882.json
```

The equivalent single command, which fetches and reviews in one go:

```bash
GITHUB_TOKEN=$(gh auth token) python -m slop_detector https://github.com/getredash/redash/pull/7882
```

`GITHUB_TOKEN` is optional for public repos. It raises GitHub's rate limit; `gh auth token` reuses your GitHub CLI login. To post the report on the PR, add `--post-comment`. That makes it public, so do it only with the maintainers' blessing.

## What the agent did

Progress printed to stderr during step 2:

```
Reviewing with ollama:gemma4:e2b-it-qat ...
  [investigator] get_pr_overview()
  [investigator] get_file_diff(redash/cli/users.py)
  [investigator] get_file_diff(redash/handlers/users.py)
  [investigator] get_file_diff(redash/models/__init__.py)
  [investigator] get_file_diff(redash/tasks/alerts.py)
```

The investigator read the overview and the 4 changed source files, but not the 2 test files (the Gemma file budget is 4). The verdict writer then produced the structured verdict below.

## Report (verbatim output)

---

## PR Slop Check: 🟢 Looks good (score 16/100)

**[getredash/redash#7882](https://github.com/getredash/redash/pull/7882)** · 6 files · +88 / -0 · by @nocode99

> The PR successfully implements the logic to skip email subscriptions for disabled users and demonstrates consistent implementation across the model, handler, and task layers. The implementation is highly focused and directly addresses the stated problem. While the core logic is correct, questions remain regarding the necessity of the CLI command and potential performance concerns with querying all user email subscriptions.

### Findings

- **[low]** The PR correctly implements the logic to skip email subscriptions for disabled users in `redash/tasks/alerts.py`, preventing unnecessary emails. (`redash/tasks/alerts.py`)
- **[low]** The PR introduces a CLI command to manage and remove disabled user email subscriptions in `redash/cli/users.py`. (`redash/cli/users.py`)
- **[low]** The model method `delete_user_email_subscriptions` correctly preserves non-email subscriptions, as described in the PR. (`model method`)

### Strengths

- The PR is highly focused and directly addresses the stated problem of preventing alert emails to disabled users.
- The implementation across the model, handler, and task layers appears consistent and correct, demonstrating a good understanding of the system's architecture.

### Questions for the author

1. Why is the CLI command `remove_disabled_alert_subscriptions` necessary if the `post` handler already handles disabling a user by deleting their email subscriptions?
2. Is there a performance concern with querying and iterating over all user email subscriptions in the `delete_user_email_subscriptions` method?

<details><summary>Heuristic signals (score 0/100, 0 fired)</summary>

No heuristic signals fired.

</details>

<sub>Flag threshold: 60. This is an automated triage aid, not a judgment of the contributor. AI-assisted work is welcome when it is correct, focused, and understood. A maintainer makes the final call.</sub>

---

## Reviewer notes (manual check of the verdict)

- **The verdict is correct.** The PR fixes a real bug: disabled users kept getting alert emails. The change is small and covered by tests on both paths. It removes and skips only email subscriptions, and keeps Slack and webhook ones because those don't notify the user. The cleanup CLI command has `--dry-run` and `--org` options.
- **Disclosed AI assistance is not penalized.** The commit carries a `Co-Authored-By: Claude Opus 5.5` trailer. No heuristic fired on it, and the work was judged on its quality, which is the intended behaviour.
- **Weak spots in the model's output**, typical for a ~2B-parameter local model:
  - The three "findings" are really positive observations.
  - Question 1 is answered by the PR description: the CLI cleans up users who were disabled before this fix.
  - Question 2 doesn't apply: the deletion is a single bulk SQL `DELETE`.
  - Edit the questions before posting them on a real PR.
