# Fix Maadi MCP bridge

This optional companion is part of the Fix Maadi agent. It exposes the same safe preparation workflow to MCP-compatible AI clients.

## Exposed interface

- Tools: `analyze_civic_report`, `list_civic_channels`, and `get_local_case`.
- Prompts: `prepare_civic_case` and `review_case_before_handoff`.
- Resources: `fix-maadi://safety-rules` and `fix-maadi://channel-registry`.

All operations are read-only or preparation-only. They do not submit complaints, open external portals, send WhatsApp, bypass login, or solve CAPTCHA.

## Run locally

Start the agent first:

```bash
cd agents/fix-maadi
python fix_maadi.py --port 8000
```

Then install and run the MCP bridge:

```bash
cd agents/fix-maadi/mcp
python -m venv .venv
source .venv/bin/activate
python -m pip install .
fix-maadi-mcp
```

Set `FIX_MAADI_URL` if the local agent uses another port. Register this command as a stdio MCP server in the client of your choice.
