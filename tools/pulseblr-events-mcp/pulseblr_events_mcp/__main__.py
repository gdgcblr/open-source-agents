"""Run the key-free PulseBLR MCP server over stdio."""

import argparse
from datetime import datetime

from .errors import InputError
from .server import create_server
from .sources import LiveSource, SampleSource


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        choices=("live", "sample"),
        default="live",
        help="live public PulseBLR service, or explicitly fictional offline sample",
    )
    parser.add_argument(
        "--now",
        metavar="ISO_TIMESTAMP",
        help="timezone-aware fixed clock, allowed only with --source sample",
    )
    args = parser.parse_args()
    now = None
    if args.now is not None:
        if args.source != "sample":
            parser.error("--now is permitted only with --source sample")
        try:
            now = datetime.fromisoformat(args.now.replace("Z", "+00:00"))
            if now.tzinfo is None or now.utcoffset() is None:
                raise ValueError
        except (ValueError, OverflowError):
            parser.error("--now requires a valid ISO timestamp including its timezone offset")
    source = SampleSource(now=now) if args.source == "sample" else LiveSource()
    try:
        create_server(source, now=now).run(transport="stdio")
    except InputError as error:
        parser.error(str(error))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
