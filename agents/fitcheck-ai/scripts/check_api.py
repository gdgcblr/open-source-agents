"""Check that your Gemini API key can reach Gemma before running FitCheck.

Usage:  python scripts/check_api.py            # list Gemma models + test default
        python scripts/check_api.py gemma-4-31b-it
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

from google import genai  # noqa: E402
from google.genai import types  # noqa: E402

from fitcheck_ai.models import HOSTED_DEFAULT, api_key  # noqa: E402


def main() -> int:
    key = api_key()
    if not key:
        print("✗ No GOOGLE_API_KEY (or GEMINI_API_KEY) found in .env or the environment.")
        print("  Create one at https://aistudio.google.com/apikey and add it to .env")
        return 1
    print(f"✓ API key found (…{key[-4:]})")

    client = genai.Client(api_key=key)
    try:
        gemmas = sorted(m.name.removeprefix("models/") for m in client.models.list()
                        if "gemma" in (m.name or "").lower())
    except Exception as exc:  # noqa: BLE001
        print(f"✗ Couldn't list models: {exc}")
        return 1
    print("✓ Gemma models your key can use:")
    for g in gemmas:
        print(f"    {g}")

    model = (sys.argv[1] if len(sys.argv) > 1 else None) or os.getenv("FITCHECK_MODEL") or HOSTED_DEFAULT
    print(f"\n→ Test call to {model} …")
    t = time.time()
    try:
        cfg = types.GenerateContentConfig(temperature=0.2, max_output_tokens=200)
        if not model.startswith("gemma-3"):
            cfg.system_instruction = "You are a concise fashion stylist."
        resp = client.models.generate_content(
            model=model, config=cfg,
            contents="In one sentence: does a navy blazer go with beige trousers?")
    except Exception as exc:  # noqa: BLE001
        print(f"✗ Call failed: {exc}")
        return 1
    answer = "".join(p.text or "" for p in resp.candidates[0].content.parts if not p.thought)
    print(f"✓ {time.time() - t:.1f}s → {answer.strip()}")
    print("\nAll good — run `python server.py` and open http://127.0.0.1:8000")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
