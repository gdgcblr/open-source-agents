"""Prepare native app access and the configured local Ollama models."""

import os
import subprocess
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv, set_key

from migine.config import Settings


def configure(project: Path):
    load_dotenv(project / ".env", override=False)
    settings = Settings.load()
    if settings.connector_url:
        raise ValueError("Unset MIGINE_MAC_CONNECTOR_URL for native local setup.")

    subprocess.run(["sh", str(project / "scripts/build-mac-helper.sh")], check=True)
    helper = project / "build/MigineConnector.app/Contents/MacOS/MigineConnector"
    if not os.getenv("MIGINE_MAC_HELPER"):
        set_key(project / ".env", "MIGINE_MAC_HELPER", str(helper))

    with httpx.Client(timeout=2, trust_env=False) as client:

        def installed_models():
            response = client.get(settings.ollama_url + "/api/tags")
            response.raise_for_status()
            return {model["name"] for model in response.json()["models"]}

        try:
            installed = installed_models()
        except httpx.ConnectError:
            print("Starting the Ollama app. Keep it running.", flush=True)
            subprocess.run(["open", "-a", "Ollama"], check=True)
            deadline = time.monotonic() + 30
            while True:
                try:
                    installed = installed_models()
                    break
                except httpx.ConnectError:
                    if time.monotonic() >= deadline:
                        raise RuntimeError("Start Ollama, then run local setup again.") from None
                    time.sleep(0.5)

    for model in (settings.chat_model, settings.embedding_model):
        tag = model if ":" in model else model + ":latest"
        if tag not in installed:
            print(f"Downloading local model: {model}", flush=True)
            subprocess.run(
                ["ollama", "pull", model],
                check=True,
                env=os.environ | {"OLLAMA_HOST": settings.ollama_url},
            )

    print("Local setup is ready. Run: sh scripts/run-local.sh")
    print("To populate financial reports, import Mail records and review extracted candidates.")


if __name__ == "__main__":
    os.umask(0o077)
    configure(Path(__file__).resolve().parents[1])
