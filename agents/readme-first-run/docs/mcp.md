# FirstRun as an MCP server

Coding agents are good at changing a project and bad at noticing that the README no longer
matches it. The MCP server lets an agent such as Claude Code or Gemini CLI ask FirstRun
"does the documented setup still work for a newcomer?" before it calls a task done.

It speaks MCP over stdio and exposes three tools:

| Tool | What it does | Runs commands? |
| :--- | :--- | :--- |
| `firstrun_plan(target, subdir?)` | The commands a newcomer would run from the README, in order, plus skipped lines with reasons and static hints | No |
| `firstrun_check(target, subdir?, sandbox="docker", offline=false, max_rounds=2, pass_env?)` | The full check: run as documented, diagnose, fix, verify in a fresh sandbox. Returns verdict, failing step, evidence, patch and the run folder | Yes |
| `firstrun_report(run_dir)` | The full `report.md` of a finished run (only folders inside FirstRun's runs folder) | No |

`target` is an absolute folder path or a GitHub URL. `sandbox="docker"` is the default and keeps the
README's commands inside a throwaway container. `sandbox="local"` runs them on your machine in a
temp folder and venv, so only use it for projects you trust. `pass_env` takes variable names (not
values) from the server's own environment and hands them to the sandbox, for projects that need an
API key. Progress (stage names, each command as it starts) is sent as MCP progress notifications.

## Setup

Install FirstRun as described in the main [README](../README.md), plus the MCP SDK:

```bash
pip install "mcp>=2.3,<3"
```

Check that the server starts (it waits for a client on stdin, stop it with Ctrl+C):

```bash
python -m firstrun.mcp_server
```

Runs are written to `runs/` next to FirstRun. Set `FIRSTRUN_RUNS_DIR` to put them somewhere else.
FirstRun's own `.env` (for `GEMINI_API_KEY`) is read on start, the same as the CLI.

## Register it with Claude Code

Use absolute paths so it works from any project. `PYTHONPATH` points at the FirstRun folder so
`python -m firstrun.mcp_server` can find the package:

```bash
claude mcp add firstrun \
  -e PYTHONPATH=/path/to/open-source-agents/agents/readme-first-run \
  -- /path/to/open-source-agents/agents/readme-first-run/.venv/bin/python -m firstrun.mcp_server
```

Then ask something like "use firstrun_check on this repo before you finish".

## Register it with Gemini CLI

Add this to `~/.gemini/settings.json` (or `.gemini/settings.json` in a project). A full check can
take a few minutes, so raise the tool timeout:

```json
{
  "mcpServers": {
    "firstrun": {
      "command": "/path/to/open-source-agents/agents/readme-first-run/.venv/bin/python",
      "args": ["-m", "firstrun.mcp_server"],
      "cwd": "/path/to/open-source-agents/agents/readme-first-run",
      "timeout": 900000
    }
  }
}
```

## Example

A real call against the bundled `examples/standup-notes` sample (local sandbox, offline rules),
with machine-specific paths shortened:

```json
{"name": "firstrun_check",
 "arguments": {"target": "/path/to/readme-first-run/examples/standup-notes", "sandbox": "local", "offline": true}}
```

Result:

```json
{
  "verdict": "fixed",
  "headline": "As documented, setup fails at step 4 (`python summarize.py notes.txt`). The suggested fix (1 change) passed from scratch in a fresh sandbox (4 steps).",
  "works_as_documented": false,
  "fix_verified": true,
  "metrics": {
    "time_to_first_success": 6.5,
    "documented_seconds": 6.7,
    "failed_at_step": 4,
    "steps_documented": 4,
    "skipped_lines": 1,
    "rounds": 1,
    "fixes_applied": 1,
    "sandbox_runs": 2,
    "total_seconds": 13.7
  },
  "failing_step": {
    "index": 4,
    "command": "python summarize.py notes.txt",
    "readme_line": 34,
    "status": "failed",
    "exit_code": 2,
    "output_tail": ".../Python: can't open file '.../work/summarize.py': [Errno 2] No such file or directory"
  },
  "diagnoses": [
    {
      "round": 1,
      "category": "wrong_command",
      "summary": "The README runs `summarize.py`, but the script is at `src/summarize.py`.",
      "confidence": "high",
      "engine": "rules",
      "blocked": false,
      "missing_env": [],
      "evidence": ["README.md:34: runs summarize.py", "src/summarize.py: actual entry point"],
      "verification": "passed"
    }
  ],
  "diff": "diff --git a/README.md b/README.md\n--- a/README.md\n+++ b/README.md\n@@ -31,7 +31,7 @@\n ## How to Run\n \n ```bash\n-python summarize.py notes.txt\n+python src/summarize.py notes.txt\n ```\n...",
  "error": null,
  "run_dir": "/path/to/readme-first-run/runs/20261024-124709-standup-notes",
  "report_md": "/path/to/readme-first-run/runs/20261024-124709-standup-notes/report.md"
}
```

The progress notifications for that call were: `understand`, `attempt`, then each command as it
started (`$ python -m venv .venv`, ...), `investigate`, `repair`, `verify` and `report`.

## Notes

- Tested with the official `mcp` Python SDK 2.3 (where `FastMCP` is called `MCPServer`). The
  server falls back to `mcp.server.fastmcp` on 1.x, but 1.x is not part of the test run.
- Nothing is printed to stdout, which carries the protocol. The startup line goes to stderr.
- `firstrun_report` refuses paths outside the runs folder, so a client cannot use it to read
  arbitrary files.
