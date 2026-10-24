import json
import os
import secrets
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import httpx

from .config import local_url
from .safety import WRITES, host_approval, validate


class NativeAdapter:
    def call(self, operation, payload, expires=None):
        if sys.platform != "darwin":
            raise RuntimeError("Native app access requires macOS or the Mac connector.")
        payload = validate(operation, payload)
        if operation == "mail.read":
            sources, skipped = [], []
            # Isolate each message so an unavailable body cannot discard readable neighbours.
            deadline = time.monotonic() + 120
            attempted = 0
            for offset in range(payload["offset"], payload["offset"] + payload["limit"]):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    skipped.append(
                        {
                            "offset": offset,
                            "count": payload["offset"] + payload["limit"] - offset,
                            "reason": "Mail scan time budget reached",
                        }
                    )
                    break
                request = json.dumps(
                    {"operation": operation, "payload": payload | {"offset": offset, "limit": 1}}
                )
                command = [
                    "/usr/bin/osascript",
                    "-l",
                    "JavaScript",
                    str(Path(__file__).with_name("native_mail.js")),
                    request,
                ]
                try:
                    attempted += 1
                    result = subprocess.run(
                        command,
                        capture_output=True,
                        text=True,
                        timeout=min(12, remaining),
                        check=True,
                    )
                    sources.extend(json.loads(result.stdout))
                except subprocess.TimeoutExpired:
                    skipped.append({"offset": offset, "count": 1, "reason": "Mail read timed out"})
            return {
                "sources": sources,
                "skipped_batches": skipped,
                "partial": bool(skipped),
                "scanned_positions": attempted,
                "requested_positions": payload["limit"],
            }
        if operation in WRITES:
            host_approval(operation, payload, expires or time.time() + 300)
        request = json.dumps({"operation": operation, "payload": payload})
        if operation.startswith("mail."):
            command = [
                "/usr/bin/osascript",
                "-l",
                "JavaScript",
                str(Path(__file__).with_name("native_mail.js")),
                request,
            ]
            result = subprocess.run(command, capture_output=True, text=True, timeout=60, check=True)
        else:
            helper = Path(
                os.getenv(
                    "MIGINE_MAC_HELPER",
                    "~/Applications/MigineConnector.app/Contents/MacOS/MigineConnector",
                )
            ).expanduser()
            if not helper.is_file():
                raise RuntimeError("Build the native helper with scripts/build-mac-helper.sh.")
            result = subprocess.run(
                [str(helper)], input=request, capture_output=True, text=True, timeout=60, check=True
            )
        return json.loads(result.stdout)


class RemoteAdapter:
    def __init__(self, settings):
        self.settings = settings

    def call(self, operation, payload, expires=None):
        payload = validate(operation, payload)
        if not self.settings.token_file:
            raise ValueError("Set MIGINE_MAC_CONNECTOR_TOKEN_FILE.")
        token = self.settings.token_file.read_text().strip()
        with httpx.Client(timeout=330, trust_env=False) as client:
            response = client.post(
                self.settings.connector_url + "/tool",
                json={
                    "operation": operation,
                    "payload": payload,
                    "expires": expires or time.time() + 300,
                },
                headers={"Authorization": "Bearer " + token},
            )
            response.raise_for_status()
            return response.json()


def adapter_for(settings):
    return RemoteAdapter(settings) if settings.connector_url else NativeAdapter()


def serve_connector(token_file, bind="127.0.0.1", port=8765):
    """Single-user host service. Keep this terminal open for approval prompts."""
    token_file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not token_file.exists():
        fd = os.open(token_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as stream:
            stream.write(secrets.token_urlsafe(48))
    if token_file.stat().st_mode & 0o077:
        raise ValueError("Connector token file must have mode 600.")
    token = token_file.read_text().strip()
    if len(token) < 32:
        raise ValueError("Connector token is too short.")
    ollama_url = local_url(os.getenv("OLLAMA_API_BASE", "http://127.0.0.1:11434"))
    proxy_paths = {
        "/ollama/api/chat": "/api/chat",
        "/ollama/api/embed": "/api/embed",
        "/ollama/api/tags": "/api/tags",
        "/v1/chat/completions": "/v1/chat/completions",
    }

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            self.connection.settimeout(330)
            if (
                self.path not in {"/tool", *proxy_paths}
                or self.headers.get("Origin") is not None
                or not secrets.compare_digest(
                    self.headers.get("Authorization", ""), "Bearer " + token
                )
            ):
                self.send_error(403)
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 131072:
                    raise ValueError("Invalid request size.")
                body = json.loads(self.rfile.read(size))
                if self.path in proxy_paths:
                    if self.path != "/ollama/api/tags":
                        name = body.get("model", "")
                        if (
                            not name.startswith(("gemma", "embeddinggemma"))
                            or "/" in name
                            or "cloud" in name
                        ):
                            raise ValueError("Only local Gemma models are permitted.")
                    with httpx.Client(timeout=300, trust_env=False) as client:
                        endpoint = ollama_url + proxy_paths[self.path]
                        response = (
                            client.get(endpoint)
                            if self.path == "/ollama/api/tags"
                            else client.post(endpoint, json=body)
                        )
                        response.raise_for_status()
                        data = response.content
                        content_type = response.headers.get("content-type", "application/json")
                    self.send_response(200)
                    self.send_header("Content-Type", content_type)
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return
                expires = float(body["expires"])
                if not time.time() < expires <= time.time() + 301:
                    raise ValueError("Invalid expiry.")
                result = NativeAdapter().call(body["operation"], body["payload"], expires)
                data = json.dumps(result).encode()
            except Exception:  # noqa: BLE001 -- HTTP boundary must not disclose private errors.
                self.send_error(400, "Operation failed, permission denied, or approval denied.")
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    print(f"Mac connector on {bind}:{port}. Keep this terminal open for approvals.", flush=True)
    HTTPServer((bind, port), Handler).serve_forever()
