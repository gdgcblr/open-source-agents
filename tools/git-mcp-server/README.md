# git-mcp-server

> A lightweight, zero-dependency Model Context Protocol (MCP) server that safely exposes Git repository status, diffs, commit history, and branches to AI assistants.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Modern AI coding agents and desktop assistants (Antigravity, Claude Desktop, Cursor) need real-time, read-only awareness of local Git state (staged diffs, branch status, commit logs) to assist developers without executing unsafe arbitrary shell commands.
- **Intended Users**: Developers who want to connect their local Git repositories to any Model Context Protocol (MCP) client.

### Key Features
- **Zero Heavy Dependencies**: Built entirely with Python's standard library and native JSON-RPC 2.0 stdio protocol.
- **5 Comprehensive Tools**:
  - `git_status`: Working tree status, staged/unstaged changes, and branch tracking.
  - `git_diff`: View staged or unstaged diffs with optional single-file filtering.
  - `git_log`: Retrieve structured commit history with configurable limit and author filtering.
  - `git_branches`: Inspect local branches, remote upstreams, and ahead/behind counts.
  - `git_show`: Inspect individual commit metadata and patch details.
- **Universal Client Compatibility**: Works out of the box with Claude Desktop, Cursor, Antigravity, Windsurf, or custom agent runners.
- **CLI Self-Test Mode**: Run `python server.py --test` to immediately verify all tools on your repository.

---

## Technical Stack

- **Language & Runtime**: Python 3.10+
- **Protocol**: Model Context Protocol (MCP) — JSON-RPC 2.0 over standard I/O (stdio)
- **External Dependencies**: None (uses standard library `json`, `subprocess`, `sys`, `os`)

---

## Prerequisites

- Python 3.10+
- `git` installed and available in `PATH`

---

## Installation & Setup

1. **Clone or navigate to the directory:**
   ```bash
   cd tools/git-mcp-server
   ```

2. **Verify functionality with the built-in self-test:**
   ```bash
   python server.py --test
   ```

---

## Connecting to MCP Clients

### 1. Claude Desktop
Add this to your `claude_desktop_config.json` (on macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "git": {
      "command": "python3",
      "args": ["/absolute/path/to/tools/git-mcp-server/server.py"]
    }
  }
}
```

### 2. Cursor or Antigravity
Configure an MCP stdio server with:
- **Command**: `python3`
- **Args**: `/absolute/path/to/tools/git-mcp-server/server.py`

---

## Example Usage & Output

### Running Self-Test (`--test`)
```text
Testing git-mcp-server tools against current directory:

--- git_status ---
## main...origin/main
 M README.md
?? src/new_module.py

--- git_branches ---
* main c84ec28 [origin/main] feat: initial release

--- git_log (latest 3) ---
c84ec28 | pydivenkat | 2026-10-24 | feat(agents): add git-commit-agent
b0ad2a4 | Kabillan T A | 2026-10-21 | Initialize repository structure

✓ All local tool checks completed successfully.
```

---

## How to Test

Run the automated test suite:
```bash
python -m unittest discover -s tests
```

---

## Security & Privacy Considerations

- **Read-Only Inspection**: Tools only execute read-only Git commands (`git status`, `git diff`, `git log`, `git branch`, `git show`). It cannot write or delete repository files.
- **Local Stdio Transport**: All communications occur over local process standard I/O; no network ports or sockets are opened.

---

## License

*Contributed under the project's open-source license.*
