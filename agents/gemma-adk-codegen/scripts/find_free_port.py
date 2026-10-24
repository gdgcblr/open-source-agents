"""Print the first available localhost TCP port at or above the requested port."""

from __future__ import annotations

import socket
import sys


def main() -> int:
    try:
        start_port = int(sys.argv[1]) if len(sys.argv) > 1 else 8501
    except ValueError:
        print("Port must be an integer.", file=sys.stderr)
        return 2

    if not 1 <= start_port <= 65535:
        print("Port must be between 1 and 65535.", file=sys.stderr)
        return 2

    for port in range(start_port, min(start_port + 100, 65536)):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as candidate:
            try:
                candidate.bind(("127.0.0.1", port))
            except OSError:
                continue
            print(port)
            return 0

    print(f"No available port found from {start_port}.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())