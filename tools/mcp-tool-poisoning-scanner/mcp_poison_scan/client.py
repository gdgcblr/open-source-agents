"""Minimal MCP clients for the stdio and Streamable HTTP transports."""

import json
import os
import queue
import shlex
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

PROTOCOL_VERSION = "2025-06-18"


class McpClientError(Exception):
    pass


def _reader(stream, lines):
    for line in stream:
        lines.put(line)
    lines.put(None)  # EOF


def _drain(stream):
    for _ in stream:
        pass


class _Session:
    def __init__(self, command, env, timeout):
        argv = shlex.split(command) if isinstance(command, str) else list(command)
        self.timeout = timeout
        self.next_id = 1
        try:
            self.proc = subprocess.Popen(
                argv,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env={**os.environ, **(env or {})},
                text=True,
                encoding="utf-8",
                bufsize=1,
            )
        except OSError as exc:
            raise McpClientError(f"Could not start server {argv[0]!r}: {exc}") from exc
        self.lines = queue.Queue()
        threading.Thread(target=_reader, args=(self.proc.stdout, self.lines), daemon=True).start()
        threading.Thread(target=_drain, args=(self.proc.stderr,), daemon=True).start()

    def send(self, message):
        try:
            self.proc.stdin.write(json.dumps(message) + "\n")
            self.proc.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise McpClientError("Server closed its input before the scan finished") from exc

    def request(self, method, params=None):
        request_id = self.next_id
        self.next_id += 1
        self.send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}})
        deadline = time.monotonic() + self.timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise McpClientError(f"Timed out after {self.timeout}s waiting for {method!r}")
            try:
                line = self.lines.get(timeout=remaining)
            except queue.Empty:
                continue
            if line is None:
                raise McpClientError(f"Server exited before answering {method!r}")
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue  # servers sometimes log to stdout; skip non-JSON lines
            if not isinstance(message, dict) or message.get("id") != request_id:
                continue  # notification or unrelated message
            if "error" in message:
                raise McpClientError(f"{method} failed: {message['error'].get('message', message['error'])}")
            return message.get("result") or {}

    def notify(self, method):
        self.send({"jsonrpc": "2.0", "method": method})

    def close(self):
        try:
            self.proc.stdin.close()
        except OSError:
            pass
        try:
            self.proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    # urllib would resend Authorization headers to wherever a redirect points.
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise McpClientError(f"Server tried to redirect to {newurl} (HTTP {code}); "
                             "redirects are not followed so credentials cannot leak. Scan that URL directly.")


def _iter_sse_messages(response, deadline):
    """Yield JSON objects from the data fields of a text/event-stream response."""
    data = []
    for raw in response:
        if time.monotonic() > deadline:
            raise McpClientError("Timed out reading event stream")
        line = raw.decode("utf-8").rstrip("\r\n")
        if line.startswith("data:"):
            data.append(line[5:].lstrip(" "))
        elif not line and data:
            try:
                yield json.loads("\n".join(data))
            except json.JSONDecodeError:
                pass
            data = []


class _HttpSession:
    def __init__(self, url, headers, timeout):
        if urllib.parse.urlparse(url).scheme not in ("http", "https"):
            raise McpClientError(f"Only http:// and https:// URLs are supported, got {url!r}")
        self.url = url
        self.headers = dict(headers or {})
        self.timeout = timeout
        self.next_id = 1
        self.session_id = None
        self.protocol_version = None
        self.opener = urllib.request.build_opener(_NoRedirect)

    def _post(self, message):
        headers = {
            **self.headers,
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "User-Agent": "mcp-poison-scan",
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        if self.protocol_version:
            headers["MCP-Protocol-Version"] = self.protocol_version
        request = urllib.request.Request(self.url, data=json.dumps(message).encode("utf-8"),
                                         headers=headers, method="POST")
        try:
            return self.opener.open(request, timeout=self.timeout)
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                challenge = exc.headers.get("WWW-Authenticate", "")
                raise McpClientError(
                    f"Server requires authentication (HTTP {exc.code}{': ' + challenge if challenge else ''}). "
                    "Pass a token with --header 'Authorization: Bearer <token>'.") from exc
            raise McpClientError(f"HTTP {exc.code} from server: {exc.reason}") from exc
        except (urllib.error.URLError, socket.timeout, ConnectionError) as exc:
            reason = getattr(exc, "reason", exc)
            raise McpClientError(f"Could not connect to {self.url}: {reason}") from exc

    def notify(self, method):
        self._post({"jsonrpc": "2.0", "method": method}).close()

    def request(self, method, params=None):
        request_id = self.next_id
        self.next_id += 1
        deadline = time.monotonic() + self.timeout
        with self._post({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}}) as response:
            self.session_id = response.headers.get("Mcp-Session-Id") or self.session_id
            content_type = response.headers.get("Content-Type", "")
            if content_type.startswith("text/event-stream"):
                messages = _iter_sse_messages(response, deadline)
            else:
                try:
                    body = json.loads(response.read().decode("utf-8") or "null")
                except json.JSONDecodeError as exc:
                    raise McpClientError(f"Server sent invalid JSON for {method!r}") from exc
                messages = body if isinstance(body, list) else [body]
            for message in messages:
                if not isinstance(message, dict) or message.get("id") != request_id:
                    continue
                if "error" in message:
                    raise McpClientError(f"{method} failed: {message['error'].get('message', message['error'])}")
                result = message.get("result") or {}
                if method == "initialize":
                    self.protocol_version = result.get("protocolVersion")
                return result
        raise McpClientError(f"Server sent no response to {method!r}")

    def close(self):
        if not self.session_id:
            return
        headers = {**self.headers, "Mcp-Session-Id": self.session_id}
        try:
            self.opener.open(urllib.request.Request(self.url, headers=headers, method="DELETE"),
                             timeout=self.timeout).close()
        except (McpClientError, urllib.error.URLError, OSError):
            pass  # ending the session is best effort


def _fetch_tools(session):
    try:
        session.request("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "mcp-poison-scan", "version": "0.1.0"},
        })
        session.notify("notifications/initialized")
        tools, cursor = [], None
        while True:
            result = session.request("tools/list", {"cursor": cursor} if cursor else {})
            tools += result.get("tools", [])
            cursor = result.get("nextCursor")
            if not cursor:
                return tools
    finally:
        session.close()


def list_tools(command, env=None, timeout=15):
    """Start a stdio MCP server, run the handshake and return all tools from tools/list."""
    return _fetch_tools(_Session(command, env, timeout))


def list_tools_http(url, headers=None, timeout=15):
    """Connect to a Streamable HTTP MCP server and return all tools from tools/list."""
    return _fetch_tools(_HttpSession(url, headers, timeout))
