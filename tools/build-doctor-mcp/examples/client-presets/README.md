# MCP Client Presets

These examples use the portable `python -m build_doctor_mcp.server` stdio command. Install the package in a virtual environment first, then replace `/absolute/path/to/your/workspace` with the workspace the MCP client is allowed to inspect.

## Presets

- `vscode-mcp.json`: VS Code MCP configuration. Place the content in `.vscode/mcp.json` under the `servers` object.
- `cursor-mcp.json`: Cursor MCP configuration. Add it to the client MCP configuration under `mcpServers`.
- `claude-desktop.json`: Claude Desktop configuration. Merge it into the `mcpServers` object in the client configuration file.

## Python Executable

If the client does not inherit the activated virtual environment, replace `python` with an absolute executable path:

- macOS/Linux: `/absolute/path/to/tools/build-doctor-mcp/.venv/bin/python`
- Windows: `C:\\absolute\\path\\to\\tools\\build-doctor-mcp\\.venv\\Scripts\\python.exe`

Do not commit personal paths or secrets. Keep `BUILD_DOCTOR_ALLOWED_ROOT` set whenever the client can access more than the intended workspace.

## First Connection Check

After connecting, call `inspect_project` with the workspace path. Then call `analyze_failure` with a sanitized failure log. Use `summarize_diagnosis` for the normal workflow and `verify_resolution` only after a developer supplies a new result.
