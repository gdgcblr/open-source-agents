#!/usr/bin/env python3
"""Verify Ollama is reachable and the configured Gemma model is pulled."""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

from rentrakshak.llm import ollama_api_base, ollama_model_tag


def main() -> int:
    base = ollama_api_base()
    tag = ollama_model_tag()
    try:
        with urllib.request.urlopen(f"{base}/api/tags", timeout=5) as resp:
            data = json.load(resp)
    except urllib.error.URLError as exc:
        print(f"Cannot reach Ollama at {base}: {exc}", file=sys.stderr)
        print("Start Ollama app or run: ollama serve", file=sys.stderr)
        return 1

    names = {m.get("name", "") for m in data.get("models", [])}
    found = tag in names or f"{tag}:latest" in names or any(tag in n for n in names)
    print(f"Ollama OK at {base}")
    print(f"Configured model: {tag}")
    print(f"Installed: {', '.join(sorted(names)) or '(none)'}")
    if not found:
        print(f"Pull model: ollama pull {tag}", file=sys.stderr)
        return 2
    print("Model appears available.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
