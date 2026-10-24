#!/usr/bin/env python3
"""
save_fixture.py — Saves a clean JSON fixture for the smoke test.

Calls the agent-sdk `read-bundled-source` tool and writes the result to
.agent-serve/fixture.json, which smoke_test.py reads.

Usage (from agents/research-brief-agent):
    python scripts/save_fixture.py
"""
import subprocess
import json
import os
import sys

# Always run from the agent root dir regardless of where the script is invoked
AGENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_PATH = os.path.join(AGENT_DIR, ".agent-serve", "fixture.json")

os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)

# Use shell=True so Windows can resolve `npx` via PATH
cmd = (
    'npx --yes @grok/agent-sdk@0.2.29 tool call read-bundled-source '
    '--dir . '
    '--input "{\\"filename\\":\\"healthcare-edge.md\\"}" '
    '--json'
)

result = subprocess.run(
    cmd,
    capture_output=True,
    text=True,
    shell=True,
    cwd=AGENT_DIR,
)

# The JSON may be multi-line; find the block starting with '{'
stdout = result.stdout
json_start = stdout.find("{")
if json_start == -1:
    print("ERROR: no JSON found in output:", file=sys.stderr)
    print("STDOUT:", stdout[:500], file=sys.stderr)
    print("STDERR:", result.stderr[:500], file=sys.stderr)
    sys.exit(1)

data = json.loads(stdout[json_start:])
with open(OUT_PATH, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f"Fixture saved to {OUT_PATH}  ok={data.get('ok')}")
