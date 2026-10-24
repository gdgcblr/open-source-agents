# Convoy MCP

> An MCP server that lets an AI assistant manage downloads in Convoy on macOS and compare completed files with a published SHA-256.

## Overview

Convoy MCP exposes download status, queueing, pause/resume/cancel, and checksum verification to MCP clients such as Gemini CLI. The server runs on macOS alongside the Convoy app. It does not discover download links or checksum files; the assistant supplies those URLs and the expected checksum.

### Key features

- Queue HTTP and HTTPS downloads in Convoy and look up the created task.
- List, pause, resume, and cancel active downloads.
- Stream-hash a completed file selected by its Convoy download ID.

## Technical stack

- **Language & runtime:** TypeScript, Node.js 20+
- **Protocol:** Model Context Protocol over stdio
- **Libraries:** `@modelcontextprotocol/sdk`, Zod
- **Download manager:** Convoy for macOS

## Architecture & data flow

The MCP server starts Convoy's signed `NativeMessagingHost` executable for each request and exchanges 4-byte little-endian length-prefixed JSON messages over stdin/stdout. The host connects to Convoy over its peer-verified local socket. MCP diagnostics go to stderr; stdout is reserved for MCP traffic.

## Prerequisites

- macOS with Convoy installed at `/Applications/Convoy.app`.
- Node.js 20 or newer and npm.
- An MCP client that supports stdio servers.

## Installation & setup

```bash
cd tools/convoy-mcp
npm install
npm run build
```

The default host path is `/Applications/Convoy.app/Contents/MacOS/NativeMessagingHost`. To use another signed Convoy installation, set `CONVOY_HOST` to its embedded `NativeMessagingHost` executable. The host must remain next to the Convoy app executable because Convoy verifies the connecting process signature.

Run the direct host connectivity probe with:

```bash
npm run ping
```

It prints the host version and whether Convoy's IPC service is reachable. `npm run ping -- --launch` asks the host to launch Convoy before returning.

## MCP client configuration

Add the built server to the MCP client's configuration, using absolute paths:

```json
{
  "mcpServers": {
    "convoy": {
      "command": "node",
      "args": ["/ABSOLUTE/PATH/open-source-agents/tools/convoy-mcp/dist/index.js"],
      "env": {
        "CONVOY_HOST": "/Applications/Convoy.app/Contents/MacOS/NativeMessagingHost"
      }
    }
  }
}
```

## How to Run

The MCP client starts the server with the command in its configuration. To launch it directly from the project directory:

```bash
npm start
```

The server uses MCP over stdio and waits for a client to communicate over stdin and stdout.

## Configuration

| Variable | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `CONVOY_HOST` | No | `/Applications/Convoy.app/Contents/MacOS/NativeMessagingHost` | Path to the signed native messaging host embedded in Convoy.app. |

## Tools

| Tool | Purpose |
| :--- | :--- |
| `convoy_status` | Check Convoy version and running state; optionally launch it. |
| `add_download` | Queue an HTTP(S) URL and return its task ID when it appears. |
| `list_downloads` | List tasks, optionally filtered by normalized status. |
| `pause_download` / `resume_download` | Control an active task by ID. |
| `cancel_download` | Cancel an active task and delete its partial download data. |
| `verify_download` | Compare a completed task's file with an expected SHA-256. |

## Example input & output

On 24 Oct 2026, an `agy` run was asked for the latest macOS LTS installer for Node.js v27. It selected the official Node.js v24.22.1 LTS installer; the [Node.js v24.22.1 archive](https://nodejs.org/en/download/archive/v24.22.1) lists the release and installer. The earlier GitHub Desktop download was left untouched.

```json
{
  "url": "https://nodejs.org/dist/v24.22.1/node-v24.22.1.pkg"
}
```

Convoy completed `node-v24.22.1.pkg` at `~/Downloads/node-v24.22.1.pkg`. `verify_download` reported:

| Check | SHA-256 |
| :--- | :--- |
| Expected, from Node.js `SHASUMS256.txt` | `ca7618402754944626787fca386c406a041541f097da172e92348d8b1e44e48b` |
| Computed by Convoy MCP | `ca7618402754944626787fca386c406a041541f097da172e92348d8b1e44e48b` |
| Result | **MATCH** |

Node.js also publishes a [detached signature](https://nodejs.org/dist/v24.22.1/SHASUMS256.txt.sig) for its checksum file.

## How to Test

Run the automated suite with the framed mock host; it does not require Convoy or macOS:

```bash
npm test
```

On macOS with Convoy installed, probe the real signed host with:

```bash
npm run ping
```

`appRunning: true` confirms the app's IPC service answered. `npm run ping -- --launch` also asks the host to launch Convoy.

## Security & privacy

- The server accepts only HTTP and HTTPS download URLs and does not accept headers, cookies, or referrers.
- Verification uses the path reported by Convoy for a task ID; the assistant cannot supply an arbitrary filesystem path.
- A connected agent can queue files onto the user's disk and can cancel downloads. Review tool calls in the MCP client before allowing them.
- A checksum obtained from the same site as a download detects accidental corruption but does not establish authenticity. For Ubuntu, verify the signed `SHA256SUMS` file with Ubuntu's signing key before relying on it.
- No credentials or secrets are required.

## Known limitations

- macOS and Convoy are required for live downloads. The mock host used by automated tests is not a substitute for the real Convoy app.
- `verify_download` requires a Convoy build whose `getDownloads` response includes each task's destination path. The corresponding change is present in the Convoy source checkout, but it must be built and installed before verification works with the installed app.
- Convoy may wait for user input on duplicate downloads. If a queued URL does not appear, the response reports that it may be waiting on a duplicate conflict dialog.
- A real `agy` run completed and verified the Node.js installer against a locally rebuilt Convoy 1.1.0 with `getDownloads` path support. The full Ubuntu Server demo still needs rehearsal.

## Future Improvements

- Add video-focused workflows, such as playlist-aware queueing and richer video metadata.
- Batch queue lecture materials—videos, slides, notes—and related resource collections.
- Verify signed checksum manifests directly instead of relying on a checksum supplied by the assistant.
- Add an integration test against a dedicated Convoy test build on macOS.

## License

This project is contributed under the repository's open-source license.
