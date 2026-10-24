# Roadmap

Built in short sprints: each sprint ends with something that works end to end, has tests and evals, and
could be submitted on its own.

## Sprint 1 - the tool (done)
- 17 rule checks, CLI with exit codes, versioned JSON report
- Optional Gemini README review with guardrails (secret gate, redaction, injection fencing, schema
  validation with one retry, retries on temporary server errors, advisory-only result)
- Evals: labelled rule cases, secret scanner vs decoys, AI review vs labelled READMEs
- **Exit criteria met**: tests and deterministic evals pass; the tool passes its own checks

## Sprint 2 - reach more people
- **MCP server** (`prcheck-mcp`): tools `check_contribution(path)` and `review_readme(path)` returning the
  JSON report, so Claude, Gemini CLI and other assistants can call it. Built on `runner.run`.
- **`prcheck pr-body`**: fills `.github/PULL_REQUEST_TEMPLATE.md` from the README and the check results.
- **Pre-push hook** example that runs `prcheck check --strict`.
- Eval: PR body vs the template (every checklist item present, no invented claims).

## Sprint 3 - fix mode (the agent)
`prcheck fix <path>` turns the tool into an agent with a bounded loop:

```
goal: every error-level check passes
loop (max 5 rounds):
  run_checks()                     -> failing checks (the checker stays the referee)
  model picks the next failure and a fix
  tool call: read_file | write_readme_section | create_env_example | add_manifest | ask_user
  show the diff -> user approves or rejects
  re-run checks; stop when green or when no progress is made
```

Built with Google ADK on top of the existing `ReviewProvider` and checks.
Guardrails: writes only inside the project folder, never edits source code, never writes real secret
values, diff plus confirmation for every change, round limit, token budget.
Evals: fix success rate on the broken eval cases, average rounds, tokens per run, % of diffs rejected.

## Sprint 4 - beyond this repository
- **Per-repo rules**: load `.prcheck.toml` from the target repo over the bundled `rules.toml`.
- **GitHub Action**: run on `pull_request`, post one summary comment, fail the job on errors.
- **Sandboxed reproducibility check**: run the README's install and test commands in a clean container
  and report whether they work. This closes the biggest gap ("it can't tell whether your code runs").

## Ongoing
- Replace seed labels in `evals/readme_golden/labels.toml` with human scores; add more labelled READMEs
  from real PRs.
- Every misfire on a real contribution becomes a new case in `evals/cases.py`.
- Track per release: rule-eval precision/recall, secret recall and false positives, AI agreement,
  latency and tokens per `--ai` run.

## Compatibility promises
- Check IDs never change meaning; retired checks keep their ID reserved.
- The JSON report's `schema_version` is bumped when a field is renamed or removed.
- `PROMPT_VERSION` is bumped whenever the review prompt or schema changes, so AI eval results stay
  comparable.
