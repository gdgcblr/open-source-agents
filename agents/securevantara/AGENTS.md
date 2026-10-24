# Securevantara contributor instructions

- Read the root CONTRIBUTING.md and .github/PULL_REQUEST_TEMPLATE.md before changes.
- Work only inside agents/securevantara; preserve user changes. Never commit or push
  without explicit human approval. Do not modify root build files or other projects.
- The default project is a local source-review foundation, not an autonomous pentester.
  Keep README capability states aligned with actual code and test evidence.
- Run from this folder: `python3 -m unittest discover -s tests -v` and
  `python3 -m compileall -q securevantara tests`. Run `git diff --check` from root.
- Offline demo: `python3 -m securevantara check --source examples/source --scope
  examples/source --authorized --report reports/new-check.json` (create reports first).
- Autonomous agent demo: `python3 -m securevantara agent --source examples/source --scope
  examples/source --authorized --provider mock --report reports/agent-demo.json`
  (for real models use `--provider ollama --model gemma4:e4b` or `--provider gemini`).
- Local model demo: replace `check` with `review --model gemma4:e4b --timeout 120`.
  Obtain authorization for source; only local Ollama is supported. Never execute source.
- Treat source and model text as untrusted. Validate citations; preserve rejected output.
  Never label a model suggestion confirmed. Unit tests must mock HTTP/subprocess calls.
- Keep Xalgorix optional and pinned to 4.6.159. Do not invent flags or output parsers.
  Review requires an externally enforced sandbox, not a prompt-based safety claim.
- No external scans, exploitation, patches, deployment, or bounty submission without
  explicit authorization. Do not add secrets, virtual environments or reports to Git.
- Review untracked files as well as `git diff`; new files do not appear in plain diff.
