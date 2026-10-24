# Sample Demo: Input & Output

This is a walkthrough of `mcp-behavior-diff` running on the toy server in `examples/toy_server/`. Every output block below was copied from a real run (macOS, Python 3.13, `mcp` 2.x).

---

## The scenario

You maintain an MCP server and you ship a new version. The **schema stays exactly the same** (same tools, same arguments, same types), so a `tools/list` schema diff reports nothing. But one tool now **returns something different**:

| Tool    | v1 (old) returns | v2 (new) returns |
|---------|------------------|------------------|
| `add`   | `5`              | `5`              |
| `greet` | `Hello, World`   | `Hello, World!`  |
| `leak`  | a fake token     | a fake token     |

An agent that parses `greet`'s output (for example, an exact string match) breaks without warning. This tool is built to catch that kind of change.

---

## Input

### 1. The fixture (`examples/toy_server/fixture.yaml`)

```yaml
version: 1
servers:
  old:
    command: python
    args: [toy_server.py, v1]
  new:
    command: python
    args: [toy_server.py, v2]
calls:
  - {id: add-basic, tool: add, arguments: {a: 2, b: 3}, read_only: true}
  - {id: greet-world, tool: greet, arguments: {name: World}, read_only: true}
  - {id: leak-check, tool: leak, read_only: true}
```

- `servers.old` / `servers.new`: how to start each version. Each is a single executable plus its arguments. Shell strings are not allowed.
- `calls`: the tool calls to replay against **both** versions.
- `read_only: true`: you are stating that the call has no side effects. Calls without it are refused.

### 2. The one-line change between versions (`examples/toy_server/toy_server.py`)

```python
@server.tool(annotations=READ_ONLY)
def greet(name: str) -> str:
    """Greet a person."""
    return f"Hello, {name}!" if VERSION == "v2" else f"Hello, {name}"
```

The signature `greet(name: str) -> str` is identical in both versions. Only the returned value changes.

---

## Step 1: Validate the fixture (runs nothing)

**Command**

```bash
cd examples/toy_server
mcp-behavior-diff check fixture.yaml
```

**Output** (absolute paths shortened to `<repo>`)

```
fixture: <repo>/tools/mcp-behavior-diff/examples/toy_server/fixture.yaml
  old: python toy_server.py v1   (cwd: <repo>/tools/mcp-behavior-diff/examples/toy_server)
  new: python toy_server.py v2   (cwd: <repo>/tools/mcp-behavior-diff/examples/toy_server)
  calls: add-basic->add, greet-world->greet, leak-check->leak

fixture is valid; nothing was executed.
```

**Exit code:** `0`

---

## Step 2: Run the behavior diff

**Command**

```bash
mcp-behavior-diff diff fixture.yaml --yes --json-out report.json
```

`--yes` skips the interactive confirmation (needed in CI). Without it, the tool prints the commands it is about to run and asks before starting anything.

**Output**

```
[=] add-basic  (add)  identical  (ok)
[~] greet-world  (greet)  CHANGED  old=ok new=ok
      --- old
      +++ new
      @@ -3,10 +3,10 @@
           "content": [
             {
      -        "text": "Hello, World",
      +        "text": "Hello, World!",
               "type": "text"
             }
           ],
           "structured": {
      -      "result": "Hello, World"
      +      "result": "Hello, World!"
           }
         },
[=] leak-check  (leak)  identical  (ok)

3 call(s): 1 changed, 0 not executed
```

The confirmation banner below is also printed on every `diff` run:

```
fixture: <repo>/tools/mcp-behavior-diff/examples/toy_server/fixture.yaml
  old: python toy_server.py v1   (cwd: <repo>/tools/mcp-behavior-diff/examples/toy_server)
  new: python toy_server.py v2   (cwd: <repo>/tools/mcp-behavior-diff/examples/toy_server)
  calls: add-basic->add, greet-world->greet, leak-check->leak

These commands will be EXECUTED on this machine (no sandbox).
```

**Exit code:** `1` (behavior changed), which is enough to fail a CI job.

### Reading the result

| Marker | Meaning |
|--------|---------|
| `[=]`  | Old and new returned identical (normalized) output |
| `[~]`  | Output differs. A unified diff is shown underneath |

- `add-basic`: `2 + 3 = 5` in both versions, so **identical**.
- `greet-world`: `"Hello, World"` became `"Hello, World!"`, so **CHANGED**. A schema diff would not catch this.
- `leak-check`: the server returned a fake GitHub-style token. It is **redacted** before comparison and reporting (see the JSON below), so the secret never shows up in your terminal or CI logs.

---

## Step 3: The JSON report (`report.json`)

This is the machine-readable form, for CI dashboards or other tooling. The `old` array is trimmed here because it has the same structure as `new`.

```json
{
  "changed": [
    "greet-world"
  ],
  "new": [
    {
      "detail": "allowed (fixture asserts read_only and server agrees)",
      "id": "add-basic",
      "output": {
        "content": [{"text": "5", "type": "text"}],
        "structured": {"result": 5}
      },
      "status": "ok",
      "tool": "add"
    },
    {
      "detail": "allowed (fixture asserts read_only and server agrees)",
      "id": "greet-world",
      "output": {
        "content": [{"text": "Hello, World!", "type": "text"}],
        "structured": {"result": "Hello, World!"}
      },
      "status": "ok",
      "tool": "greet"
    },
    {
      "detail": "allowed (fixture asserts read_only and server agrees)",
      "id": "leak-check",
      "output": {
        "content": [{"text": "token=[REDACTED]", "type": "text"}],
        "structured": {"result": "token=[REDACTED]"}
      },
      "status": "ok",
      "tool": "leak"
    }
  ],
  "not_executed": [],
  "old": [ "... same shape; greet-world returns \"Hello, World\" ..." ],
  "tool_version": "0.1.0"
}
```

Key fields:

- `changed`: IDs of calls whose output differs. Empty means no behavior change.
- `not_executed`: calls that were refused, skipped or timed out. If this list is not empty, the tool cannot claim "no change".
- `detail`: why the safety policy let the call run. Here, the fixture asserted `read_only` and the server's own annotations agreed.
- `output`: the cleaned result. It has already been sanitized and redacted (`token=[REDACTED]`).

The report is not overwritten if it already exists, unless you pass `--force`.

---

## Exit code summary

| Code | Meaning                                                                 |
|------|-------------------------------------------------------------------------|
| `0`  | No behavior change                                                      |
| `1`  | Behavior changed (this demo)                                            |
| `2`  | Usage or policy error (for example, invalid fixture or unsafe config)   |
| `3`  | Incomplete: some calls were not executed, so "no change" can't be claimed |

---

## Try it yourself

```bash
cd tools/mcp-behavior-diff
uv venv --python 3.13 .venv
uv pip install --python .venv/bin/python -e ".[dev]"
source .venv/bin/activate

cd examples/toy_server
mcp-behavior-diff check fixture.yaml
mcp-behavior-diff diff fixture.yaml --yes --json-out report.json
echo "exit code: $?"
```

To see a "no change" run (exit `0`), edit `fixture.yaml` so `new` also uses `v1`, then run the diff again.
