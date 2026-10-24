# PR Agent

A local agent built on Google ADK. It watches GitHub pull requests, judges whether each feature is worth having and how well it's built, and waits for your approval. Once approved, it implements the change in an isolated git worktree on your machine, runs your checks, and makes a limited number of repair attempts.

It never merges, pushes, deploys or publishes anything.

## Setup (once)

1. Install [Ollama](https://ollama.com/download) and pull the model:
   ```
   ollama pull qwen2.5-coder:3b
   ```
2. Create a fine-grained GitHub token with read-only **Contents** and **Pull requests** access, and put it in `.env`:
   ```
   GITHUB_TOKEN=github_pat_...
   ```
3. Edit `config.yaml` and set `repos:` to your repository, e.g. `- name: yourname/yourrepo`.
   Cloning uses your SSH key (`git@github.com:...`). You can set `clone_url` to use HTTPS instead.
4. Check that everything is reachable:
   ```
   .venv\Scripts\python -m pr_agent --check
   ```

The `.venv` is already set up with Python 3.12. To rebuild it: `uv venv --python 3.12 .venv` then `uv pip install --python .venv\Scripts\python.exe -r requirements.txt`.

## Run

```
.venv\Scripts\python -m pr_agent
```

Open http://127.0.0.1:8765. Click a PR to see its evaluation, then choose **Implement locally** or **Skip**.

## How it works

| Step | Who does it |
|---|---|
| Poll GitHub, skip revisions already handled, apply filters | Deterministic code (`pipeline.py`) |
| Scan the diff for red flags (eval, process execution, secrets, CI or dependency changes) | Deterministic code (`prescan`) |
| Score feature value and code quality separately; assign category, risk and recommendation | **PR Evaluator** agent (ADK) |
| Your approval, tied to the exact commit SHA | Dashboard → `Engine.approve` |
| Re-check the PR on GitHub before starting; stop if it changed | Deterministic code |
| Create a worktree from the base branch, with pushing disabled on the clone | `workspace.py` |
| Write an implementation plan | **Planning** agent |
| Apply the PR patch or write the change, using tools confined to the worktree | **Implementation** agent |
| Run the checks (configured or auto-detected) | Deterministic code + `policy.py` |
| Diagnose failures and fix them, up to `max_repair_attempts` | **Verification** agent |
| Report changed files, the diff, check results and remaining issues | Dashboard |

## Safety

- **Local-only by default.** `strict_local: true` refuses to start with any model that isn't an Ollama model served from localhost. Code, diffs and prompts stay on your machine. The only network traffic is GitHub API calls and git fetches.
- **Restricted commands.** Every command goes through an allowlist in `policy.py`: `python -m pytest/ruff/mypy/compileall`, `npm test`, `npm run lint|build|typecheck`, `go test`, `cargo test` and similar. Shell operators are rejected, nothing runs through a shell, and secrets are removed from the environment.
- **Repository content is untrusted.** Prompts wrap it in `<untrusted>` tags and tell the model not to follow instructions inside them. File tools can't leave the worktree or touch `.git`.
- **Approval is tied to a revision.** New commits cancel the approval, and the PR has to be re-evaluated.
- **Restarts are safe.** Runs that were in progress get marked *interrupted* and are never resumed blindly.
- **Honest outcomes.** Each result is one of `passed`, `checks_failing`, `unverified` (no checks found) or `no_changes`.
- **Approved implementations run tests from the PR.** The allowlist limits which commands can be launched, but the tests themselves are the PR's own code. Only approve PRs whose code you're willing to run on your machine.

## Limits on this hardware

With 8 GB of RAM and a 2 GB GPU, a 3B model is the practical ceiling. Evaluations will be rough, and implementation depends mostly on applying the PR's own patch. If you get more memory, change `model` to something like `ollama_chat/qwen2.5-coder:7b`.

## Tests

```
.venv\Scripts\python -m pytest -q
```

The tests cover the command policy, local-only enforcement, skipping repeat revisions, approval rules, restart recovery and workspace confinement. One end-to-end test runs approval → worktree → patch → pytest → report against a local git remote, with the model stubbed out.
