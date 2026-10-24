"""Verify a local Ollama API and model tag before starting the app container."""

from __future__ import annotations

import json
import os
import sys
from urllib.error import URLError
from urllib.request import urlopen


def main() -> int:
    base_url = os.getenv("OLLAMA_API_BASE", "http://localhost:11434").rstrip("/")
    model_tag = os.getenv("OLLAMA_MODEL_TAG", "gemma3:latest")
    try:
        with urlopen(f"{base_url}/api/tags", timeout=4) as response:
            payload = json.load(response)
    except (OSError, URLError, json.JSONDecodeError) as exc:
        print(
            f"Cannot reach Ollama at {base_url}: {exc}\n"
            "Start Ollama and confirm its API is listening on port 11434.",
            file=sys.stderr,
        )
        return 1

    installed = {
        model.get("name")
        for model in payload.get("models", [])
        if isinstance(model, dict) and isinstance(model.get("name"), str)
    }
    if model_tag not in installed:
        available = ", ".join(sorted(installed)) or "none"
        print(
            f"Ollama is reachable, but model '{model_tag}' is not installed. "
            f"Available models: {available}.\n"
            f"Install it locally with: ollama pull {model_tag}",
            file=sys.stderr,
        )
        return 1

    print(f"Local Ollama is ready: {model_tag} ({base_url})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())