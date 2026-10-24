import os
from typing import Callable
from urllib.parse import parse_qs, urlencode
from wsgiref.simple_server import WSGIRequestHandler, make_server

LOCAL_CALLBACK_URL = "http://127.0.0.1:8765/callback"


def application(environ: dict, start_response: Callable) -> list[bytes]:
    path = environ.get("PATH_INFO", "")
    if path == "/health":
        body = b"ok"
        start_response(
            "200 OK",
            [
                ("Content-Type", "text/plain; charset=utf-8"),
                ("Content-Length", str(len(body))),
                ("Cache-Control", "no-store"),
            ],
        )
        return [body]
    if path != "/callback":
        body = b"Not found."
        start_response(
            "404 Not Found",
            [
                ("Content-Type", "text/plain; charset=utf-8"),
                ("Content-Length", str(len(body))),
                ("Cache-Control", "no-store"),
            ],
        )
        return [body]
    if environ.get("REQUEST_METHOD") != "GET":
        body = b"Method not allowed."
        start_response(
            "405 Method Not Allowed",
            [
                ("Content-Type", "text/plain; charset=utf-8"),
                ("Content-Length", str(len(body))),
                ("Allow", "GET"),
                ("Cache-Control", "no-store"),
            ],
        )
        return [body]

    query = parse_qs(environ.get("QUERY_STRING", ""), keep_blank_values=True)
    if (
        len(environ.get("QUERY_STRING", "")) > 8192
        or any(len(values) != 1 for values in query.values())
        or not query.get("state", [""])[0]
        or not (query.get("code", [""])[0] or query.get("error", [""])[0])
    ):
        body = b"Invalid LinkedIn callback. Return to the app and try again."
        start_response(
            "400 Bad Request",
            [
                ("Content-Type", "text/plain; charset=utf-8"),
                ("Content-Length", str(len(body))),
                ("Cache-Control", "no-store"),
                ("Referrer-Policy", "no-referrer"),
            ],
        )
        return [body]

    forwarded = {
        key: query[key][0]
        for key in ("code", "state", "error")
        if key in query
    }
    location = LOCAL_CALLBACK_URL + "?" + urlencode(forwarded)
    start_response(
        "302 Found",
        [
            ("Location", location),
            ("Content-Length", "0"),
            ("Cache-Control", "no-store"),
            ("Referrer-Policy", "no-referrer"),
        ],
    )
    return [b""]


class QuietRequestHandler(WSGIRequestHandler):
    def log_message(self, _format: str, *args) -> None:
        return


def main() -> None:
    port = int(os.getenv("PORT", "10000"))
    with make_server("0.0.0.0", port, application, handler_class=QuietRequestHandler) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()
