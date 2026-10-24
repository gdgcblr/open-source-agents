#!/usr/bin/env python3
"""
Helper: run the agent-sdk tool call and save clean JSON fixture.
Usage (from agents/research-brief-agent):
    python scripts/save_fixture.py
"""
import subprocess
import json
import os
import sys

# Always run from the agent root dir
AGENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.makedirs(os.path.join(AGENT_DIR, ".agent-serve"), exist_ok=True)

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

# The JSON output may be multi-line; find the block starting with '{'
stdout = result.stdout
json_start = stdout.find("{")
if json_start == -1:
    print("ERROR: no JSON found in output:", file=sys.stderr)
    print("STDOUT:", stdout[:500], file=sys.stderr)
    sys.exit(1)

data = json.loads(stdout[json_start:])
out_path = os.path.join(AGENT_DIR, ".agent-serve", "nvidia-fixture.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f"Fixture saved to {out_path}  ok={data.get('ok')}")
