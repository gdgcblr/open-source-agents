---
description: Record a narrated demo video of a running web app
argument-hint: "[url] [--scenes N] [--voice <name>] [--out <dir>]"
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, Task
---

Record a narrated demo video of a running web app.

Arguments: `$ARGUMENTS`

Parse them as: a URL (optional — if absent, look for a dev server in this repo's
README or package.json scripts and ask the user to confirm the URL before
continuing), `--scenes N` (default 10), `--voice <name>` (default
`en-US-AriaNeural`), `--out <dir>` (default `./autodemo-out`).

Follow the `autodemo` skill. In short:

1. **Preflight.** Run `autodemo preflight` against the URL. If the app is not
   reachable, stop and tell the user to start it — do not try to start it
   yourself.

2. **Script it.** Spawn the `demo-scripter` subagent with the URL, the scene
   count, the voice and the output dir. It explores the app, writes
   `autodemo.config.yaml`, dry-runs it, and repairs its own failing steps.

3. **Show the narration and stop.** Print the proposed narration scene by scene
   as plain prose — not YAML — along with the dry-run result and anything the
   scripter left out. Then **ask the user to approve or edit it, and wait.**
   Do not render before they answer. A full render costs real minutes and the
   narration is what they will want to change.

4. **Render on approval.** `autodemo render --config <path>`. Report the output
   path, the duration, and any steps skipped during the real run.

If the user asks for a specific change to the narration, edit the config
directly rather than re-running the scripter — it is faster and keeps the
selectors that already dry-ran clean.
