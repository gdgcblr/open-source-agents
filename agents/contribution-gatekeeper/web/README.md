# Gatekeeper web console

A browser front end for the gatekeeper: review a PR or a local folder, browse findings with their fix commands and rule citations, preview the PR comment, and triage many PRs on one board.

```bash
# from agents/contribution-gatekeeper, with the project's venv active
python web/server.py          # http://127.0.0.1:8765  (pass a port to change it)
```

- **Live mode** (server running): paste a PR URL (`https://github.com/OWNER/REPO/pull/N`) or a local path and press Review. "Gemini reviewers" is available when `GOOGLE_API_KEY` is set. "Fresh-install sandbox" is available when Docker is running.
- **Offline mode** (no API server, e.g. `python -m http.server -d web` on a laptop without the venv): the three bundled demo reports still work, and you can open or drop any report produced by `gatekeeper review … --json report.json` or `gatekeeper triage … ` (its `.json`).

The server binds to `127.0.0.1` only, because it runs `git` (and optionally Docker) on this machine. It handles one review at a time.

## Demo reports

`web/demo/*.json` are produced by running the real deterministic checks on three synthetic PRs (ready, changes requested, blocked):

```bash
python web/make_demo_reports.py
```

They are marked `"demo": true` and labelled "Demo fixture" in the console. No network or LLM is used.

## Report format

The console reads the JSON from `report.to_json()` (what `--json` writes): `submission` {url, title, author, number, project_dir, changed_files}, `verdict`, `score`, `scores`, `llm_used`, `sandbox`, `notes`, `review_markdown`, `findings[]`. Older reports with only the flat keys (`url`, `number`, `title`, `author`, `project`) also work. Demo reports also carry `policy`, which the How it works page shows. A JSON array of reports opens as a triage board.
