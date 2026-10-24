"""Writes a haiku about any topic using the Gemini API."""

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def load_env_file(path=Path(__file__).with_name(".env")):
    # tiny .env reader so the project needs no dependencies
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def get_api_key():
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key or key.startswith("<") or key.lower().startswith("your"):
        sys.exit(
            "error: missing API key. Set GEMINI_API_KEY in .env or your shell "
            "(get one at https://aistudio.google.com/apikey)."
        )
    return key


def write_haiku(topic, key, model):
    prompt = f"Write one haiku (5-7-5 syllables) about: {topic}. Reply with only the three lines."
    body = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode("utf-8")
    request = urllib.request.Request(
        API_URL.format(model=model),
        data=body,
        headers={"Content-Type": "application/json", "x-goog-api-key": key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.load(response)
    except urllib.error.HTTPError as err:
        detail = err.read().decode("utf-8", "replace")[:300]
        sys.exit(f"error: Gemini API returned {err.code}: {detail}")
    except urllib.error.URLError as err:
        sys.exit(f"error: could not reach the Gemini API ({err.reason})")
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError):
        sys.exit("error: Gemini returned no haiku, try another topic")


def main(argv):
    if len(argv) < 2:
        sys.exit('usage: python haiku.py "your topic"')
    load_env_file()
    key = get_api_key()
    model = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")
    topic = " ".join(argv[1:])
    haiku = write_haiku(topic, key, model)
    print(f"Topic: {topic}")
    print(haiku)


if __name__ == "__main__":
    main(sys.argv)
